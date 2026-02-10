# HuntX Development Guide

## Project Structure

```
src/huntx/
├── bot/                  # GatherX Telegram bot (DM-based, 13 commands)
│   └── interactive.py    # InteractiveBot: /start /get /latest /formats /protocols /count
│                         #   /setformat /myinfo /status /mute /unmute /ping /help
├── cli/                  # CLI entry points
│   └── main.py           # huntx CLI: run, bot, clean, reset subcommands
├── config/               # Configuration loading & validation
│   ├── env_expand.py     # ${VAR} expansion
│   ├── loader.py         # YAML → AppConfig
│   ├── schema.py         # Pydantic v2 models
│   └── validate.py       # Cross-reference validation
├── connectors/           # Source connectors (media filtering + configurable fetch windows)
│   ├── base.py           # Protocol definitions
│   ├── telegram/         # Bot API connector
│   └── telegram_user/    # MTProto (Telethon) connector
├── core/                 # Orchestration & routing
│   ├── locks.py          # Cross-platform file locking
│   ├── orchestrator.py   # Main pipeline (N-worker pool, 6 phases)
│   └── router.py         # Format detection by extension/content (20+ proxy URI schemes)
├── formats/              # Format handlers (12 total)
│   ├── base.py           # FormatHandler protocol
│   ├── common/           # Shared utilities (hashing, normalization)
│   ├── registry.py       # Singleton handler registry
│   ├── register_builtin.py
│   ├── npvt.py           # Proxy URIs (vmess/vless/trojan/ss/ssr/hysteria2/tuic/wireguard/socks/etc.)
│   ├── npvtsub.py        # .npvtsub subscription files
│   ├── conf_lines.py     # Generic line-based configs
│   ├── opaque_bundle.py  # Binary → ZIP archive (base class)
│   ├── ovpn.py, npv4.py, ehi.py, hc.py, hat.py, sip.py, nm.py, dark.py  # Opaque subclasses
├── pipeline/             # Processing stages
│   ├── ingest.py         # Download + save raw blobs (with progress logging)
│   ├── transform.py      # Batch parse raw → records (200/batch, batch DB writes)
│   ├── build.py          # Merge records → artifacts + full protocol decode + base64 re-encode
│   └── publish.py        # Send artifacts to Telegram
├── publishers/
│   └── telegram/publisher.py  # Multipart file upload
├── state/                # SQLite state management
│   ├── db.py             # Connection pool + migrations
│   ├── repo.py           # StateRepo (CRUD + batch insert/update)
│   └── schema.sql        # DDL
├── store/                # File storage
│   ├── paths.py          # Global path configuration
│   ├── raw_store.py      # SHA-256 sharded blob store
│   ├── artifact_store.py # Output + archive + internal artifacts
│   └── rejects.py        # Rejected file storage
├── utils/
│   └── atomic.py         # Cross-platform atomic file writes
└── logging_conf.py       # Logging setup
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e .
pip install pytest black flake8 mypy
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Code Quality

```bash
black src/ tests/
flake8 src/ tests/ --max-line-length 120
mypy src/ --ignore-missing-imports
```

## Key Design Decisions

- **Queue-based worker pool**: Workers pull sources from `queue.Queue` — guarantees no two workers process the same source without explicit locking
- **Atomic writes**: All file writes go through `atomic_write()` using `os.replace()` for cross-platform safety
- **SQLite with WAL**: Concurrent reads are safe; writes use 30s timeout for thread contention
- **Format registry singleton**: Handlers registered once at startup; looked up by format ID at runtime
- **Batch transform**: Files processed in batches of 200 with `executemany` for record inserts and status updates — avoids per-record DB round-trips
- **Full protocol decode**: `build.py` decodes all proxy URI schemes (vmess, ss, ssr via base64; vless, trojan, hysteria2, tuic, wireguard, socks, etc. via URL parse) into structured JSON
- **Re-encoding**: Plain-text proxy URI lists are also re-encoded as base64 subscription blobs for v2rayN/v2rayNG client compatibility
- **Media filtering**: Both connectors drop images/videos/GIFs/stickers/voice/audio before downloading, keeping only text, documents, and text+document hybrids
- **Configurable fetch windows**: 4 separate lookback parameters (msg fresh, file fresh, msg subsequent, file subsequent) threaded from CLI → orchestrator → connectors

## GatherX Bot Architecture

The bot (`src/huntx/bot/interactive.py`) has two modes:

- **`deliver_updates()`** — fire-and-forget: connect, send all output files to all non-muted users, disconnect. Called automatically after every `huntx run`.
- **`start()`** — persistent: registers 13 command handlers, listens forever for DM commands.

User state is stored in the `bot_users` SQLite table:
- Auto-registered on first `/start`
- `default_format` column for per-user preferences (`/setformat`)
- `muted` flag for opt-out (`/mute` / `/unmute`)
- `last_delivered_at` for delivery tracking

## Adding a New Format

1. Create `src/huntx/formats/myformat.py`:
   - Extend `OpaqueBundleHandler` for binary formats
   - Implement `FormatHandler` protocol for text formats
2. Add routing in `src/huntx/core/router.py`
3. Register in `src/huntx/formats/register_builtin.py`
4. Add tests in `tests/test_formats_coverage.py` and `tests/test_router.py`
5. Update `SUPPORTED_FORMATS` in `src/huntx/bot/interactive.py`
6. Add to `_ZIP_FORMATS` in `pipeline/publish.py` if binary

## Adding a New Proxy Protocol

1. Add URI scheme to `_PROXY_SCHEMES` in `formats/npvt.py`
2. Add scheme to `_PROXY_URI_PREFIXES` in `core/router.py`
3. Add decoder in `pipeline/build.py::_decode_single_line()` — use `_parse_standard_uri()` for standard URI formats or add custom decoder for base64/encoded formats
4. Add scheme to `_PROXY_SCHEMES` in `pipeline/build.py`

## Adding a New Connector

1. Implement `SourceConnector` protocol from `connectors/base.py`
2. Accept `fetch_windows` dict in constructor
3. Add connector instantiation in `orchestrator.py::_ingest_one_source()`
4. Add source type to `config/schema.py::SourceConfig`
5. Add validation in `config/schema.py` field validator

## Adding a New Bot Command

1. Add handler method `_on_<command>` in `src/huntx/bot/interactive.py`
2. Register event handler in `start()` method
3. Add `BotCommand(...)` entry to `_BOT_COMMANDS` list
4. Update `WELCOME_TEXT` help string
5. Add test in `tests/test_bot_interactive.py`
