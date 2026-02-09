# HUNTX

Lightweight, zero-budget, incremental proxy-config aggregator and Telegram publisher. Scrapes configuration files (V2Ray, OpenVPN, WireGuard, Hysteria, TUIC, etc.) from multiple Telegram channels, deduplicates and merges them, then republishes unified subscriptions.

## Features

- **Multi-source ingestion** — Bot API and MTProto User Session connectors
- **Configurable worker pool** — parallel ingestion via `HUNTX_MAX_WORKERS`
- **12 format handlers** — `npvt`, `npvtsub`, `ovpn`, `npv4`, `conf_lines`, `ehi`, `hc`, `hat`, `sip`, `nm`, `opaque_bundle`, plus content-based detection
- **20+ proxy protocols** — vmess, vless, trojan, ss, ssr, hysteria2, tuic, wireguard, socks, juicity, anytls, warp, dns, and more
- **Full protocol decoding** — all proxy URIs decoded to structured JSON; base64 subscription re-encoding
- **Incremental & deduplicated** — SHA-256 content hashing, only new files processed
- **Media filtering** — images, videos, GIFs, stickers, voice, audio automatically dropped
- **APK safety filter** — `.apk` files automatically rejected
- **Batch transform** — files processed in batches of 200 with batch DB writes for efficiency
- **Interactive bot** — `/latest`, `/status`, `/run`, `/formats`, `/subscribe`, `/unsubscribe`, `/clean`
- **3 CLI commands** — `run` (pipeline), `bot` (persistent bot), `clean` (wipe all data)
- **Customizable fetch windows** — separate lookback for text/files on fresh vs subsequent runs
- **Zero-budget CI** — runs on GitHub Actions with SQLite state persisted to a git branch
- **Cross-platform** — works on Linux, macOS, and Windows

## Quick Start

```bash
git clone https://github.com/your-username/HUNTX.git
cd HUNTX
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Copy and edit the config:

```bash
cp configs/config.prod.yaml my_config.yaml
export TELEGRAM_TOKEN="your-bot-token"
```

For MTProto user session (history + public channels):

```bash
python scripts/make_telethon_session.py
```

Run the pipeline:

```bash
HUNTX --config my_config.yaml run
```

Run the interactive bot persistently:

```bash
HUNTX bot
```

Wipe all data for a fresh start:

```bash
HUNTX clean
```

## CLI Commands

### `HUNTX run`

Run the full pipeline (ingest → transform → build → publish → cleanup).

| Flag | Description | Default |
|---|---|---|
| `--msg-fresh-hours N` | Text lookback hours for first-seen source | `2` |
| `--file-fresh-hours N` | File lookback hours for first-seen source | `48` |
| `--msg-subsequent-hours N` | Text lookback on subsequent runs (0=all new) | `0` |
| `--file-subsequent-hours N` | File lookback on subsequent runs (0=all new) | `0` |
| `--bot-timeout N` | Run bot for N seconds after pipeline | `0` (skip) |

### `HUNTX bot`

Run the interactive Telegram bot persistently (stays connected, responds to commands).

| Flag | Description | Default |
|---|---|---|
| `--token` | Bot token | `PUBLISH_BOT_TOKEN` or `TELEGRAM_TOKEN` |
| `--api-id` | Telegram API ID | `TELEGRAM_API_ID` |
| `--api-hash` | Telegram API hash | `TELEGRAM_API_HASH` |

### `HUNTX clean`

Delete all data, state, cache, and logs for a fresh start.

| Flag | Description |
|---|---|
| `--yes` / `-y` | Skip confirmation prompt |

## Architecture

```
Sources (Telegram)
    │  ┌──────────────┐
    ├──│ Worker 1      │──► Ingest ──► Raw Store
    ├──│ Worker 2      │──► Ingest ──► Raw Store
    ├──│ ...           │──► ...
    └──│ Worker N      │──► Ingest ──► Raw Store
       └──────────────┘
                │
        Transform (batch format detection + parse)
                │
        Build (merge + deduplicate per route)
                │
          ┌─────┴─────────────────┐
     Publish       Decode          Re-encode
     (Telegram)    (JSON artifact)  (base64 sub)
```

**Pipeline phases:**
1. **Ingest** — N workers pull sources from a shared queue (no duplicates), media filtered early
2. **Transform** — batch processing (200 files/batch), format detection, parse into records, batch DB writes
3. **Build** — merge records per route/format, decode proxy URIs to JSON, re-encode as base64 subscription
4. **Publish** — send changed artifacts to destination channels
5. **Cleanup** — prune processed raw blobs and old archives

## Supported Formats

### Text-based (single file, line-per-record)

| Format ID | Extension | Client | Description |
|---|---|---|---|
| `npvt` | `.txt` / auto | v2rayN/NG, Xray, sing-box | Proxy URI lines (20+ protocols) |
| `npvtsub` | `.npvtsub` | NapsternetV | Subscription proxy URIs |
| `conf_lines` | `.conf` | Generic | Line-based config entries |

### Binary/opaque (ZIP archive)

| Format ID | Extension | Client | Description |
|---|---|---|---|
| `ovpn` | `.ovpn` | OpenVPN | OpenVPN config files |
| `npv4` | `.npv4` | NapsternetV v4 | Encrypted VPN config |
| `ehi` | `.ehi` | HTTP Injector | Encrypted SSH/proxy config |
| `hc` | `.hc` | HTTP Custom | Tunnel VPN config |
| `hat` | `.hat` | HA Tunnel Plus | SSH/SSL/HTTP proxy config |
| `sip` | `.sip` | SocksIP Tunnel | SOCKS tunnel config |
| `nm` | `.nm` | NetMod VPN | SSH/V2Ray/OpenVPN/DNSTT config |
| `opaque_bundle` | fallback | N/A | Unrecognized binary files |

## Supported Proxy Protocols

vmess, vless, trojan, shadowsocks (ss), shadowsocksR (ssr), hysteria2/hy2, hysteria, tuic, wireguard/wg, socks/socks4/socks5, anytls, juicity, warp, dns/dnstt

## Configuration

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for full configuration reference.

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `TELEGRAM_TOKEN` | Bot API token for ingestion | — |
| `PUBLISH_BOT_TOKEN` | Bot token for publishing (optional) | — |
| `TELEGRAM_API_ID` | MTProto API ID | — |
| `TELEGRAM_API_HASH` | MTProto API hash | — |
| `TELEGRAM_USER_SESSION` | Telethon session string | — |
| `HUNTX_MAX_WORKERS` | Parallel ingestion workers | `2` |
| `HUNTX_BOT_TIMEOUT` | Post-pipeline bot window (seconds) | `0` |
| `HUNTX_DATA_DIR` | Data directory path | `./data` |
| `HUNTX_STATE_DB_PATH` | SQLite DB path | `./data/state/state.db` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for contribution guidelines.

## License

MIT
