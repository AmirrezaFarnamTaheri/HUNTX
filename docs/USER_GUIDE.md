# MergeBot User Guide

## Table of Contents

1. [Configuration](#configuration)
2. [Supported Formats](#supported-formats)
3. [Running Locally](#running-locally)
4. [Running on GitHub Actions](#running-on-github-actions)
5. [Telegram User Session (MTProto)](#telegram-user-session-mtproto)
6. [Interactive Bot](#interactive-bot)
7. [Architecture](#architecture)
8. [Output Artifacts](#output-artifacts)

## Configuration

MergeBot is controlled by a YAML configuration file with environment variable expansion (`${VAR}`).

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
      formats: ["npvt"]
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

| Format ID | Extension | Type | Description |
|---|---|---|---|
| `npvt` | `.txt`, auto-detect | Text | V2Ray/VLESS/Trojan/SS proxy URIs |
| `npvtsub` | `.npvtsub` | Text | Subscription files with proxy URIs |
| `ovpn` | `.ovpn` | Binary | OpenVPN configs (zipped) |
| `npv4` | `.npv4` | Binary | NPV4 configs (zipped) |
| `conf_lines` | `.conf` | Text | Generic line-based configs |
| `ehi` | `.ehi` | Binary | EHI tunnel configs (zipped) |
| `hc` | `.hc` | Binary | HTTP Custom configs (zipped) |
| `hat` | `.hat` | Binary | HTTP Advanced Tunnel configs (zipped) |
| `sip` | `.sip` | Binary | SIP configs (zipped) |
| `opaque_bundle` | fallback | Binary | Any unrecognized binary files (zipped) |

All binary formats produce ZIP archives. Text formats produce deduplicated plain-text files.

## Running Locally

```bash
mergebot --config configs/config.prod.yaml --data-dir ./data --db-path ./data/state/state.db run
```

Set `MERGEBOT_MAX_WORKERS` to control parallelism (default: 10):

```bash
MERGEBOT_MAX_WORKERS=5 mergebot --config my_config.yaml run
```

## Running on GitHub Actions

1. **Fork the repository**
2. **Add Secrets** (Settings → Secrets → Actions):
   - `TELEGRAM_TOKEN` — Bot API token for ingestion
   - `PUBLISH_BOT_TOKEN` — separate bot token for publishing (optional)
   - `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_USER_SESSION` — for MTProto
3. **Enable the workflow** — `.github/workflows/mergebot.yml` runs every 3 hours
4. **Manual trigger** — use "Run workflow" with custom `max_workers` input
5. State is persisted on an orphan branch `mergebot-state`

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

The bot processes commands during each scheduled run (30-second window).

| Command | Description |
|---|---|
| `/start`, `/help` | Show help message |
| `/latest [format] [days]` | Get latest artifacts (default: all, 4 days) |
| `/status` | Pipeline statistics (sources, files, records) |
| `/formats` | List all supported formats |
| `/subscribe <format> [hours]` | Auto-deliver every N hours (default: 6) |
| `/unsubscribe [format]` | Remove subscription(s) |

## Architecture

```
Sources → [Worker Pool (N=10)] → Ingest → Raw Store (SHA-256 sharded)
                                              ↓
                                    Transform (format detect + parse)
                                              ↓
                                    Build (merge + deduplicate)
                                         ↓          ↓
                                    Publish    V2Ray Decode
                                  (Telegram)   (local artifact)
                                         ↓
                                    Cleanup (prune raw + archive)
```

Workers pull from a shared queue — no two workers process the same source.

## Output Artifacts

| Path | Description |
|---|---|
| `output/{route}.{fmt}` | Latest merged artifact per route/format |
| `output/{route}.npvt.decoded.json` | Decoded V2Ray links (local only, never published) |
| `archive/{route}_{timestamp}.{fmt}` | Timestamped archive copies |
| `dist/` | Packaged output for GitHub Actions upload |

### Verification

```bash
python scripts/verify_output.py
```

Validates output files, decodes VMess links, and optionally runs V2Ray config checks.
