# MergeBot

Lightweight, zero-budget, incremental proxy-config aggregator and Telegram publisher. Scrapes configuration files (V2Ray, OpenVPN, etc.) from multiple Telegram channels, deduplicates and merges them, then republishes unified subscriptions.

## Features

- **Multi-source ingestion** — Bot API and MTProto User Session connectors
- **2-worker parallel pool** — configurable via `MERGEBOT_MAX_WORKERS`
- **11 format handlers** — `npvt`, `npvtsub`, `ovpn`, `npv4`, `conf_lines`, `ehi`, `hc`, `hat`, `sip`, `opaque_bundle`, plus content-based detection
- **V2Ray link decoding** — decoded JSON artifact saved locally (never published)
- **Incremental & deduplicated** — SHA-256 content hashing, only new files processed
- **APK safety filter** — `.apk` files automatically rejected
- **Interactive bot** — `/latest`, `/status`, `/formats`, `/subscribe`, `/unsubscribe`
- **Zero-budget CI** — runs on GitHub Actions with SQLite state persisted to a git branch
- **Cross-platform** — works on Linux, macOS, and Windows

## Quick Start

```bash
git clone https://github.com/your-username/mergebot.git
cd mergebot
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

Run:

```bash
mergebot --config my_config.yaml run
```

## Architecture

```
Sources (Telegram)
    │  ┌──────────────┐
    ├──│ Worker 1      │──► Ingest ──► Raw Store
    ├──│ Worker 2      │──► Ingest ──► Raw Store
    ├──│ ...           │──► ...
    └──│ Worker N (2)  │──► Ingest ──► Raw Store
       └──────────────┘
                │
        Transform (format detection + parse)
                │
        Build (merge + deduplicate per route)
                │
          ┌─────┴─────┐
     Publish       Decode (V2Ray JSON artifact)
     (Telegram)    (local only)
```

**Pipeline phases:**
1. **Ingest** — N workers pull sources from a shared queue (no duplicates)
2. **Transform** — detect format, parse into records, deduplicate
3. **Build** — merge records per route/format, save artifacts
4. **Publish** — send changed artifacts to destination channels
5. **Cleanup** — prune processed raw blobs and old archives

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
| `MERGEBOT_MAX_WORKERS` | Parallel ingestion workers | `2` |
| `MERGEBOT_DATA_DIR` | Data directory path | `./data` |
| `MERGEBOT_STATE_DB_PATH` | SQLite DB path | `./data/state/state.db` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for contribution guidelines.

## License

MIT
