# MergeBot User Guide

## Table of Contents
1. [Configuration](#configuration)
2. [Running locally](#running-locally)
3. [Running on GitHub Actions](#running-on-github-actions)
4. [Architecture](#architecture)

## Configuration

The core of MergeBot is controlled by a YAML configuration file.

### Sources

Define where the bot should look for files.

```yaml
sources:
  - id: "source_channel_1"
    type: "telegram"
    selector:
      include_formats: ["npvt", "ovpn"]
    telegram:
      token: "${TELEGRAM_TOKEN}"
      chat_id: "-1001234567890"
```

### Publishing Routes

Define how to merge and where to publish the results.

```yaml
publishing:
  routes:
    - name: "merged_vpn"
      from_sources: ["source_channel_1"]
      formats: ["npvt"]
      destinations:
        - chat_id: "-1009876543210"
          mode: "post_on_change"
          caption_template: "Merged V2Ray Configs\nDate: {timestamp}"
```

## Running Locally

To run the bot manually:

```bash
mergebot --config configs/config.prod.yaml --data-dir ./data --db-path ./data/state/state.db run
```

## Running on GitHub Actions

MergeBot is designed to run periodically on GitHub Actions without a dedicated server.

1. **Fork the repository**.
2. **Add Secrets**:
   - Go to Settings -> Secrets and variables -> Actions.
   - Add `TELEGRAM_TOKEN` (for the scraping bot).
   - Add `PUBLISH_BOT_TOKEN` (if using a separate bot for publishing).
3. **Enable Workflows**:
   - The `.github/workflows/mergebot.yml` workflow is scheduled to run hourly.
   - It will automatically create an orphan branch `mergebot-state` to store the SQLite database between runs.

## Architecture

- **Ingestion**: The bot connects to Telegram, downloads new files, and computes a SHA256 hash.
- **Deduplication**: Files with known hashes are skipped.
- **Transformation**: Files are parsed into a normalized format (if supported) or treated as opaque blobs.
- **Merging**: Compatible formats are combined into a single artifact.
- **Publishing**: The merged artifact is sent to the destination channel.

## Recent Updates

### 72-Hour Fresh Start Logic
When a Telegram source is added for the first time (or if the database state is reset), the bot will now default to fetching messages from the last **723600 seconds** (approx 8.3 days). This prevents fetching extremely old history while ensuring recent content is captured.

### Multi-Format Output
The bot now generates user-friendly output files in the `persist/data/output` directory.
- Files are named as `{route_name}.{format}` (e.g., `demo_output.npvt`).
- These are separate from the internal hashed artifacts.

### Verification Script
A verification script is included in the GitHub Artifacts output.
- Locate `verify_output.py` in the downloaded artifact zip.
- Run it locally to validate the integrity of your proxy files:
  ```bash
  python verify_output.py
  ```
