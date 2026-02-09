# HUNTX User Guide

## Table of Contents

1. [Configuration](#configuration)
2. [Supported Formats](#supported-formats)
3. [Supported Proxy Protocols](#supported-proxy-protocols)
4. [Running Locally](#running-locally)
5. [CLI Commands](#cli-commands)
6. [Running on GitHub Actions](#running-on-github-actions)
7. [Telegram User Session (MTProto)](#telegram-user-session-mtproto)
8. [Interactive Bot](#interactive-bot)
9. [Media Filtering](#media-filtering)
10. [Architecture](#architecture)
11. [Output Artifacts](#output-artifacts)

## Configuration

HUNTX is controlled by a YAML configuration file with environment variable expansion (`${VAR}`).

### Sources

#### Bot API Source

For private channels where the bot is an admin:

```yaml
sources:
  - id: "source_channel_1"
    type: "telegram"
    selector:
      include_formats: ["all"]
    telegram:
      token: "${TELEGRAM_TOKEN}"
      chat_id: "-1001234567890"
```

#### MTProto User Source

For public channels, message history, and text content:

```yaml
sources:
  - id: "public_channel"
    type: "telegram_user"
    selector:
      include_formats: ["npvt", "npvtsub", "conf_lines"]
    telegram_user:
      api_id: ${TELEGRAM_API_ID}
      api_hash: "${TELEGRAM_API_HASH}"
      session: "${TELEGRAM_USER_SESSION}"
      peer: "@ChannelName"
```

### Publishing Routes

```yaml
publishing:
  routes:
    - name: "merged_vpn"
      from_sources: ["source_channel_1", "public_channel"]
      formats:
        - npvt
        - npvtsub
        - conf_lines
        - ovpn
        - npv4
        - ehi
        - hc
        - hat
        - sip
        - nm
        - opaque_bundle
      destinations:
        - chat_id: "-1009876543210"
          mode: "post_on_change"
          caption_template: "Merged configs — {timestamp}"
```

### Selector: `include_formats`

Use `["all"]` to accept every format, or list specific IDs:

```yaml
selector:
  include_formats: ["npvt", "npvtsub", "ovpn", "ehi"]
```

## Supported Formats

| Format ID | Extension | Type | Client | Description |
|---|---|---|---|---|
| `npvt` | `.txt`, auto-detect | Text | v2rayN/NG, Xray, sing-box | Proxy URI lines (20+ protocols) |
| `npvtsub` | `.npvtsub` | Text | NapsternetV | Subscription proxy URIs |
| `conf_lines` | `.conf` | Text | Generic | Line-based config entries |
| `ovpn` | `.ovpn` | Binary (ZIP) | OpenVPN | OpenVPN config files |
| `npv4` | `.npv4` | Binary (ZIP) | NapsternetV v4 | Encrypted VPN config |
| `ehi` | `.ehi` | Binary (ZIP) | HTTP Injector | Encrypted SSH/proxy config |
| `hc` | `.hc` | Binary (ZIP) | HTTP Custom | Tunnel VPN config |
| `hat` | `.hat` | Binary (ZIP) | HA Tunnel Plus | SSH/SSL/HTTP proxy config |
| `sip` | `.sip` | Binary (ZIP) | SocksIP Tunnel | SOCKS tunnel config |
| `nm` | `.nm` | Binary (ZIP) | NetMod VPN | SSH/V2Ray/OpenVPN/DNSTT config |
| `opaque_bundle` | fallback | Binary (ZIP) | N/A | Unrecognized binary files |

All binary formats produce ZIP archives. Text formats produce deduplicated plain-text files.

For `npvt` and `npvtsub`, the build phase also produces:
- **`.decoded.json`** — structured JSON with all proxy URIs fully parsed
- **`.b64sub`** — base64-encoded subscription (standard for v2rayN/v2rayNG import)

## Supported Proxy Protocols

All of the following URI schemes are detected, parsed, and decoded:

| Scheme | Protocol | Decoding |
|---|---|---|
| `vmess://` | VMess (V2Ray) | Base64 → JSON |
| `vless://` | VLESS (V2Ray/Xray) | Standard URI parse |
| `trojan://` | Trojan | Standard URI parse |
| `ss://` | Shadowsocks | SIP002 base64 userinfo or legacy base64 |
| `ssr://` | ShadowsocksR | Full base64 decode → structured fields |
| `hysteria2://` / `hy2://` | Hysteria 2 | Standard URI parse |
| `hysteria://` | Hysteria 1 | Standard URI parse |
| `tuic://` | TUIC (QUIC) | Standard URI parse |
| `wireguard://` / `wg://` | WireGuard | Standard URI parse |
| `socks://` / `socks5://` / `socks4://` | SOCKS proxy | Standard URI parse |
| `anytls://` | AnyTLS (sing-box) | Standard URI parse |
| `juicity://` | Juicity (QUIC) | Standard URI parse |
| `warp://` | Cloudflare WARP | Standard URI parse |
| `dns://` / `dnstt://` | DNS tunnel | Standard URI parse |

## Running Locally

```bash
HUNTX --config configs/config.prod.yaml run
```

Set `HUNTX_MAX_WORKERS` to control parallelism (default: 2):

```bash
HUNTX_MAX_WORKERS=5 HUNTX --config my_config.yaml run
```

## CLI Commands

### `HUNTX run`

Run the full pipeline (ingest → transform → build → publish → cleanup).

```bash
HUNTX --config my_config.yaml run [OPTIONS]
```

| Flag | Description | Default |
|---|---|---|
| `--msg-fresh-hours N` | Text lookback hours for first-seen source | `2` |
| `--file-fresh-hours N` | File lookback hours for first-seen source | `48` |
| `--msg-subsequent-hours N` | Text lookback on subsequent runs (0=all new) | `0` |
| `--file-subsequent-hours N` | File lookback on subsequent runs (0=all new) | `0` |
| `--bot-timeout N` | Run interactive bot for N seconds after pipeline | `0` (skip) |

### `HUNTX bot`

Run the interactive Telegram bot persistently (stays connected, responds to commands).

```bash
HUNTX bot [--token TOKEN] [--api-id ID] [--api-hash HASH]
```

Credentials default to `PUBLISH_BOT_TOKEN`/`TELEGRAM_TOKEN`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`.

### `HUNTX clean`

Delete all data, state, cache, and logs for a fresh start.

```bash
HUNTX clean [--yes]
```

Deletes: raw store, output, archive, state DB, rejects, and logs.

## Running on GitHub Actions

1. **Fork the repository**
2. **Add Secrets** (Settings → Secrets → Actions):
   - `TELEGRAM_TOKEN` — Bot API token for ingestion
   - `PUBLISH_BOT_TOKEN` — separate bot token for publishing (optional)
   - `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_USER_SESSION` — for MTProto
3. **Enable the workflow** — `.github/workflows/HUNTX.yml` runs every 3 hours
4. **Manual trigger** — use "Run workflow" with custom `max_workers` input
5. State is persisted on an orphan branch `HUNTX-state`

## Telegram User Session (MTProto)

Unlocks history access, public channel reading, and text content ingestion.

### Setup

1. Go to [my.telegram.org](https://my.telegram.org) → API development tools → create an app
2. Generate session string:
   ```bash
   python scripts/make_telethon_session.py
   ```
3. Save as `TELEGRAM_USER_SESSION` in GitHub Secrets or env vars

## Interactive Bot

The bot can run persistently (`HUNTX bot`) or briefly after each pipeline run (`--bot-timeout`).

| Command | Description |
|---|---|
| `/start`, `/help` | Show help message |
| `/latest [format] [days]` | Get latest artifacts (default: all, 4 days) |
| `/status` | Pipeline statistics (sources, files, records) |
| `/run` | Show last pipeline run info per source |
| `/formats` | List all supported formats |
| `/subscribe <format> [hours]` | Auto-deliver every N hours (default: 6) |
| `/unsubscribe [format]` | Remove subscription(s) |
| `/clean` | Show cleanup instructions |

The bot registers its command menu via `setMyCommands` on startup, so commands appear in the Telegram menu.

## Media Filtering

Both connectors automatically drop messages containing unwanted media types **before** downloading:

**Dropped**: images, videos, GIFs/animations, stickers, voice messages, audio, video notes

**Kept**: text-only messages, document-only messages, text+document hybrid messages

This significantly reduces bandwidth and processing time for channels that mix proxy configs with media posts.

## Architecture

```
Sources → [Worker Pool (N)] → Ingest → Raw Store (SHA-256 sharded)
                                              ↓
                                    Transform (batch: 200 files/batch)
                                              ↓
                                    Build (merge + deduplicate)
                                    ↓          ↓            ↓
                               Publish    Decode JSON    Re-encode b64
                             (Telegram)   (structured)   (subscription)
                                    ↓
                               Cleanup (prune raw + archive)
```

Workers pull from a shared queue — no two workers process the same source. Transform uses batch DB writes (`executemany`) for efficiency.

## Output Artifacts

| Path | Description |
|---|---|
| `output/{route}.{fmt}` | Latest merged artifact per route/format |
| `output/{route}.npvt.decoded.json` | All proxy URIs decoded to structured JSON |
| `output/{route}.npvt.b64sub` | Base64-encoded subscription (v2rayN/v2rayNG compatible) |
| `archive/{route}_{timestamp}.{fmt}` | Timestamped archive copies |
| `dist/` | Packaged output for GitHub Actions upload |

### Verification

```bash
python scripts/verify_output.py
```

Validates output files, decodes proxy links, and optionally runs V2Ray config checks.
