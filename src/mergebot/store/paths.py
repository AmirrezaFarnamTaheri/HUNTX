import os
from pathlib import Path

# Base directory for all data
# Can be overridden by env var MERGEBOT_DATA_DIR
DATA_DIR = Path(os.getenv("MERGEBOT_DATA_DIR", "data")).resolve()

# Specific subdirectories
RAW_STORE_DIR = DATA_DIR / "raw"
ARTIFACT_STORE_DIR = DATA_DIR / "artifacts"
REJECTS_DIR = DATA_DIR / "rejects"
STATE_DIR = DATA_DIR / "state"
LOGS_DIR = DATA_DIR / "logs"

STATE_DB_PATH = STATE_DIR / "state.db"

def ensure_dirs():
    """Create all necessary directories."""
    for d in [DATA_DIR, RAW_STORE_DIR, ARTIFACT_STORE_DIR, REJECTS_DIR, STATE_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
