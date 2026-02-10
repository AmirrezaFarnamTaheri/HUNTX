# HuntX

**HuntX** is a zero-budget, incremental proxy-config aggregation pipeline. It scrapes VPN/proxy configuration files (V2Ray, OpenVPN, WireGuard, Hysteria, TUIC, etc.) from 49+ Telegram channels, deduplicates and merges them, then delivers unified subscriptions via the **GatherX** Telegram bot.

## Features

- **Multi-source ingestion** — Bot API and MTProto User Session connectors (49+ sources)
- **Configurable worker pool** — parallel ingestion via `HUNTX_MAX_WORKERS`
- **12 format handlers** — `npvt`, `npvtsub`, `ovpn`, `npv4`, `conf_lines`, `ehi`, `hc`, `hat`, `sip`, `nm`, `dark`, `opaque_bundle`
- **20+ proxy protocols** — vmess, vless, trojan, ss, ssr, hysteria2, tuic, wireguard, socks, juicity, anytls, warp, dns, and more
- **Full protocol decoding** — all proxy URIs decoded to structured JSON; base64 subscription re-encoding
- **Incremental & deduplicated** — SHA-256 content hashing, only new files processed
- **Media filtering** — images, videos, GIFs, stickers, voice, audio automatically dropped
- **APK safety filter** — `.apk` files automatically rejected
- **Batch transform** — files processed in batches of 200 with batch DB writes
- **GatherX bot** — DM-based interactive Telegram bot with 13 commands, user preferences, auto-delivery
- **4 CLI commands** — `run` (pipeline + auto-deliver), `bot` (persistent bot), `clean`, `reset`
- **Configurable fetch windows** — separate lookback for text/files on fresh vs subsequent runs (tunable from CI)
- **Factory reset** — full wipe of state, data, outputs, and source offsets (CLI + CI trigger)
- **48h rolling dev output** — deduplicated proxy URIs accumulated with timestamps in `outputs_dev/`
- **Zero-budget CI** — runs on GitHub Actions every 3h with SQLite state on an orphan branch
- **Cross-platform** — Linux, macOS, Windows

## Quick Start

```bash
git clone https://github.com/your-username/huntx.git
cd huntx
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

Run the pipeline (auto-delivers to all GatherX bot users after completion):

```bash
huntx --config my_config.yaml run
```

Run the GatherX bot persistently:

```bash
huntx bot
```

## CLI Commands

### `huntx run`

Run the full pipeline (ingest → transform → build → publish → auto-deliver → cleanup).

| Flag | Description | Default |
|---|---|---|
| `--msg-fresh-hours N` | Text lookback hours for first-seen source | `2` |
| `--file-fresh-hours N` | File lookback hours for first-seen source | `48` |
| `--msg-subsequent-hours N` | Text lookback on subsequent runs (0=all new) | `0` |
| `--file-subsequent-hours N` | File lookback on subsequent runs (0=all new) | `0` |
| `--no-deliver` | Skip automatic subscription delivery after pipeline | — |

After the pipeline completes, all output files are automatically sent to every registered GatherX bot user (unless `--no-deliver` is passed).

### `huntx bot`

Run the GatherX bot in persistent interactive mode (listens forever for DM commands).

| Flag | Description | Default |
|---|---|---|
| `--token` | Bot token | `PUBLISH_BOT_TOKEN` or `TELEGRAM_TOKEN` |
| `--api-id` | Telegram API ID | `TELEGRAM_API_ID` |
| `--api-hash` | Telegram API hash | `TELEGRAM_API_HASH` |

### `huntx clean`

Delete all data, state, cache, and logs for a fresh start.

| Flag | Description |
|---|---|
| `--yes` / `-y` | Skip confirmation prompt |

### `huntx reset`

Full factory reset — wipes ALL data, state, caches, outputs, and source offsets. More thorough than `clean`.

| Flag | Description |
|---|---|
| `--yes` / `-y` | Skip confirmation prompt (otherwise requires typing `RESET`) |

## GatherX Bot

**GatherX** is the user-facing Telegram bot. Anyone can DM it to register and receive proxy configs.

### How It Works

1. User sends `/start` → auto-registered + receives latest proxy list
2. After every pipeline run → bot auto-sends all outputs to every registered user
3. Users can request specific formats on demand with `/get`
4. Users can `/mute` to opt out, `/unmute` to opt back in

### Bot Commands

| Command | Description |
|---|---|
| `/start` | Register and receive latest configs |
| `/get [format]` | Download configs (default: your preferred format) |
| `/latest [days]` | Get all recent artifacts (default: 4 days) |
| `/formats` | List all supported formats |
| `/protocols` | Show supported proxy protocols |
| `/count` | Proxy URI count per protocol (with bar chart) |
| `/setformat <fmt>` | Set your preferred default format |
| `/myinfo` | Your account info and preferences |
| `/status` | Pipeline statistics (sources, files, records, users) |
| `/mute` | Stop auto-delivery |
| `/unmute` | Resume auto-delivery |
| `/ping` | Check if bot is alive |
| `/help` | Show help message |

## Architecture

```
Sources (49+ Telegram channels)
    │  ┌──────────────┐
    ├──│ Worker 1      │──► Ingest ──► Raw Store
    ├──│ Worker 2      │──► Ingest ──► Raw Store
    └──│ Worker N      │──► Ingest ──► Raw Store
       └──────────────┘
                │
        Transform (batch: 200 files/batch, format detection)
                │
        Build (merge + deduplicate per route, per format)
                │
          ┌─────┴──────────────────────┐
     Publish       Decode          Re-encode        GatherX Bot
     (Telegram)    (JSON artifact)  (base64 sub)    (auto-deliver DMs)
```

**Pipeline phases:**
1. **Ingest** — N workers pull sources from a shared queue, media filtered early
2. **Transform** — batch format detection + parse into records, batch DB writes
3. **Build** — merge records per route/format, decode proxy URIs to JSON, re-encode as base64 subscription
4. **Publish** — send changed artifacts to destination channels
5. **Deliver** — auto-send outputs to all registered GatherX bot users
6. **Cleanup** — prune processed raw blobs and old archives

## Supported Formats

### Text-based

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
| `dark` | `.dark` | Dark Tunnel VPN | Dark tunnel config |
| `opaque_bundle` | fallback | N/A | Unrecognized binary files |

### Derived outputs

For `npvt` routes, the build phase also produces:
- **`_decoded.json`** — structured JSON with all proxy URIs fully parsed
- **`_b64sub.txt`** — base64-encoded subscription (v2rayN/v2rayNG import)

## Supported Proxy Protocols

vmess, vless, trojan, shadowsocks (ss), shadowsocksR (ssr), hysteria2/hy2, hysteria, tuic, wireguard/wg, socks/socks4/socks5, anytls, juicity, warp, dns/dnstt

## GitHub Actions CI

The workflow (`.github/workflows/huntx.yml`) runs every 3 hours and supports manual dispatch with these inputs:

| Input | Description | Default |
|---|---|---|
| `max_workers` | Parallel ingestion workers | `2` |
| `msg_fresh_hours` | Text lookback for first-seen sources | `2` |
| `file_fresh_hours` | File/media lookback for first-seen sources | `48` |
| `msg_subsequent_hours` | Text lookback on subsequent runs | `0` |
| `file_subsequent_hours` | File/media lookback on subsequent runs | `0` |
| `reset` | Factory reset before run (checkbox) | `false` |

State is persisted on the `huntx-state` orphan branch.

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `TELEGRAM_TOKEN` | Bot API token for ingestion | — |
| `PUBLISH_BOT_TOKEN` | Bot token for GatherX (optional, falls back to `TELEGRAM_TOKEN`) | — |
| `TELEGRAM_API_ID` | MTProto API ID | — |
| `TELEGRAM_API_HASH` | MTProto API hash | — |
| `TELEGRAM_USER_SESSION` | Telethon session string | — |
| `HUNTX_MAX_WORKERS` | Parallel ingestion workers | `2` |
| `HUNTX_DATA_DIR` | Data directory path | `./data` |
| `HUNTX_STATE_DB_PATH` | SQLite DB path | `./data/state/state.db` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Configuration

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for full configuration reference.

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for contribution guidelines.

## License

MIT
