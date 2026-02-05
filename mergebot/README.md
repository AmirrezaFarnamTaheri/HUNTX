# MergeBot

MergeBot is a lightweight, zero-budget, incremental file merger and publisher for Telegram. It aggregates configuration files (like V2Ray, OpenVPN) from multiple Telegram channels, deduplicates them, merges them into unified subscriptions, and republishes them.

## Key Features

- **Multi-Source Ingestion**: Scrapes files from Telegram channels.
- **Incremental Processing**: Only processes new files since the last run.
- **Format Support**:
  - `npvt` (V2Ray/VLESS)
  - `ovpn` (OpenVPN)
  - `conf_lines` (Generic line-based configs)
  - `opaque_bundle` (Zipped binary blobs)
- **Zero-Budget Architecture**: Designed to run on ephemeral GitHub Actions runners with state persistence committed to a git branch.
- **Privacy Focused**: No external databases required; state is kept in a local SQLite file.

## Quick Start

### 1. Installation

```bash
git clone https://github.com/your-username/mergebot.git
cd mergebot
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configuration

Copy the example config and edit it:

```bash
cp configs/config.prod.yaml my_config.yaml
```

Set your environment variables:

```bash
export TELEGRAM_TOKEN="your-bot-token"
```

### 3. Run

```bash
mergebot --config my_config.yaml run
```

## Documentation

- [User Guide](docs/USER_GUIDE.md): Detailed configuration and usage instructions.
- [Development Guide](DEVELOPMENT.md): How to contribute to the project.

## License

MIT
