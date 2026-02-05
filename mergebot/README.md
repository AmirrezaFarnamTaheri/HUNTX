# MergeBot

Incremental multi-format file merger and Telegram publisher.

## Features

- **Ingest**: Fetches files from Telegram channels.
- **Transform**: Normalizes text configurations or handles binary blobs (ZIP bundling).
- **Build**: Merges unique records, deduplicating by content across sources.
- **Publish**: Sends updates to Telegram only when content changes (Atomic Publishing).
- **Robustness**:
  - Uses SHA256 content addressing.
  - SQLite state management.
  - Handles Telegram file size limits (20MB).

## Installation

```bash
cd mergebot
pip install -e .
```

## Configuration

Edit `configs/config.prod.yaml` or create your own.

Key sections:
- **sources**: Define Telegram channels to scrape.
  - `include_formats`: Whitelist formats (e.g. `["npvt", "conf_lines"]` or `["all"]`).
- **publishing**: Define output routes.
  - `from_sources`: Which sources to aggregate.
  - `destinations`: Where to post the result.

## Usage

1. **Initialize the Database** (Run once):
   ```bash
   mkdir -p data/state
   python3 -c "import sqlite3; conn = sqlite3.connect('data/state/state.db'); conn.executescript(open('src/mergebot/state/schema.sql').read())"
   ```

2. **Run the Bot**:
   ```bash
   export TELEGRAM_TOKEN="your_token_here"
   mergebot --config configs/config.prod.yaml run
   ```

## Architecture

- **RawStore**: Stores original files by SHA256.
- **StateRepo**: Tracks ingestion status and parsed records in SQLite.
- **ArtifactStore**: Stores built outputs.
- **Pipeline**: Ingest -> Transform -> Build -> Publish.
