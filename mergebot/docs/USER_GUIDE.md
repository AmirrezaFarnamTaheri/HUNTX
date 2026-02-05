# MergeBot User Guide

MergeBot is a tool for aggregating, merging, and republishing files from Telegram channels. It supports various proxy configuration formats (v2ray, ovpn, etc.) and handles binary blobs efficiently.

## 1. Installation

### Prerequisites
- Python 3.11+
- Git
- A Linux server (or environment)

### Steps

1. **Clone the repository:**
   ```bash
   git clone <repo_url>
   cd mergebot
   ```

2. **Install dependencies:**
   ```bash
   # It is recommended to use a virtual environment
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

## 2. Configuration

The application is configured via a YAML file (e.g., `configs/config.prod.yaml`).

### Structure

```yaml
sources:
  - id: "channel_alpha"
    type: "telegram"
    selector:
      include_formats: ["npvt", "conf_lines"] # or ["all"]
    telegram:
      token: "${TELEGRAM_TOKEN}"       # Uses env var
      chat_id: "-100123456789"         # Channel ID to scrape

publishing:
  routes:
    - name: "merged_output"
      from_sources: ["channel_alpha"]
      formats: ["npvt"]                # Format to build
      destinations:
        - chat_id: "-100987654321"     # Where to publish
          mode: "post_on_change"
          token: "${PUBLISH_BOT_TOKEN}" # Optional: diff bot for publishing
          caption_template: "Updated: {timestamp} | Count: {count}"
```

## 3. First Run

1. **Initialize the Database:**
   Run this command once to create the SQLite schema:
   ```bash
   mkdir -p data/state
   python3 -c "import sqlite3; conn = sqlite3.connect('data/state/state.db'); conn.executescript(open('src/mergebot/state/schema.sql').read())"
   ```

2. **Set Environment Variables:**
   ```bash
   export TELEGRAM_TOKEN="123456:ABC-DEF..."
   ```

3. **Run the Bot:**
   ```bash
   mergebot --config configs/config.prod.yaml run
   ```

## 4. Deployment (Systemd)

A systemd service file is provided in `scripts/systemd/mergebot.service`.

1. **Edit the service file:**
   - Update paths to match your installation (e.g., `/opt/mergebot`).
   - Ensure the user `mergebot` exists or change to your user.

2. **Install and Start:**
   ```bash
   sudo cp scripts/systemd/mergebot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now mergebot
   ```

3. **Logs:**
   Check logs with:
   ```bash
   journalctl -u mergebot -f
   ```

## 5. Troubleshooting

- **Database Locks**: If the bot crashes, ensure no other instance is running. The bot uses a file lock `data/state/mergebot.lock`.
- **Telegram Limits**: The bot automatically skips files larger than 20MB.
- **Unknown Formats**: Files that don't match specific parsers are treated as "opaque bundles" and will be zipped if the route format is `opaque_bundle`.
