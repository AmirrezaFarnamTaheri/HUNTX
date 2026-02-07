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

STATE_DB_PATH = Path(os.getenv("MERGEBOT_STATE_DB_PATH", str(STATE_DIR / "state.db"))).resolve()

def ensure_dirs():
    """Create all necessary directories."""
    for d in [DATA_DIR, RAW_STORE_DIR, ARTIFACT_STORE_DIR, REJECTS_DIR, STATE_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def set_paths(data_dir: str, db_path: str):
    """
    Sets the global path variables and environment variables.

    Args:
        data_dir: The base data directory.
        db_path: The path to the state database file.
    """
    global DATA_DIR, RAW_STORE_DIR, ARTIFACT_STORE_DIR, REJECTS_DIR, STATE_DIR, LOGS_DIR, STATE_DB_PATH

    d = Path(data_dir).resolve()

    # Update environment variables for consistency
    os.environ["MERGEBOT_DATA_DIR"] = str(d)
    os.environ["MERGEBOT_STATE_DB_PATH"] = str(Path(db_path).resolve())

    DATA_DIR = d
    RAW_STORE_DIR = DATA_DIR / "raw"
    ARTIFACT_STORE_DIR = DATA_DIR / "artifacts"
    REJECTS_DIR = DATA_DIR / "rejects"
    STATE_DIR = DATA_DIR / "state"
    LOGS_DIR = DATA_DIR / "logs"

    STATE_DB_PATH = Path(db_path).resolve()
