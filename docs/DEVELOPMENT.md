# MergeBot Development Guide

## Project Structure

```
src/mergebot/
├── bot/                  # Interactive Telegram bot
│   └── interactive.py
├── cli/                  # CLI entry points
│   ├── main.py           # mergebot CLI (argparse)
│   └── commands/run.py   # run subcommand
├── config/               # Configuration loading & validation
│   ├── env_expand.py     # ${VAR} expansion
│   ├── loader.py         # YAML → AppConfig
│   ├── schema.py         # Pydantic v2 models
│   └── validate.py       # Cross-reference validation
├── connectors/           # Source connectors
│   ├── base.py           # Protocol definitions
│   ├── telegram/         # Bot API connector
│   └── telegram_user/    # MTProto (Telethon) connector
├── core/                 # Orchestration & routing
│   ├── locks.py          # Cross-platform file locking
│   ├── orchestrator.py   # Main pipeline (2-worker pool)
│   └── router.py         # Format detection by extension/content
├── formats/              # Format handlers
│   ├── base.py           # FormatHandler protocol
│   ├── common/           # Shared utilities (hashing, normalization)
│   ├── registry.py       # Singleton handler registry
│   ├── register_builtin.py
│   ├── npvt.py           # V2Ray/VLESS/Trojan URIs
│   ├── npvtsub.py        # .npvtsub subscription files
│   ├── conf_lines.py     # Generic line-based configs
│   ├── opaque_bundle.py  # Binary → ZIP archive
│   ├── ovpn.py, npv4.py, ehi.py, hc.py, hat.py, sip.py
├── pipeline/             # Processing stages
│   ├── ingest.py         # Download + save raw blobs
│   ├── transform.py      # Parse raw → records
│   ├── build.py          # Merge records → artifacts + V2Ray decode
│   └── publish.py        # Send artifacts to Telegram
├── publishers/
│   └── telegram/publisher.py  # Multipart file upload
├── state/                # SQLite state management
│   ├── db.py             # Connection pool + migrations
│   ├── repo.py           # StateRepo (CRUD for all tables)
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
- **V2Ray decode artifacts**: `build.py` decodes vmess/vless/trojan links into JSON but never publishes them — they're local artifacts only

## Adding a New Format

1. Create `src/mergebot/formats/myformat.py`:
   - Extend `OpaqueBundleHandler` for binary formats
   - Implement `FormatHandler` protocol for text formats
2. Add routing in `src/mergebot/core/router.py`
3. Register in `src/mergebot/formats/register_builtin.py`
4. Add tests in `tests/test_formats_coverage.py` and `tests/test_router.py`
5. Update `SUPPORTED_FORMATS` in `src/mergebot/bot/interactive.py`

## Adding a New Connector

1. Implement `SourceConnector` protocol from `connectors/base.py`
2. Add connector instantiation in `orchestrator.py::_ingest_one_source()`
3. Add source type to `config/schema.py::SourceConfig`
4. Add validation in `config/schema.py` field validator
