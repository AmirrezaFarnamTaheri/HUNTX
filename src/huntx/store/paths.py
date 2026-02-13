import os
from pathlib import Path


def _read_env(primary: str, legacy: str, default: str) -> str:
    value = os.getenv(primary)
    if value is not None:
        return value
    legacy_value = os.getenv(legacy)
    if legacy_value is not None:
        return legacy_value
    return default


# Base directory for all data
# Can be overridden by env var HUNTX_DATA_DIR (or legacy huntx_DATA_DIR)
DATA_DIR = Path(_read_env("HUNTX_DATA_DIR", "huntx_DATA_DIR", "data")).resolve()

# Specific subdirectories
RAW_STORE_DIR = DATA_DIR / "raw"
ARTIFACT_STORE_DIR = DATA_DIR / "artifacts"
REJECTS_DIR = DATA_DIR / "rejects"
STATE_DIR = DATA_DIR / "state"
LOGS_DIR = DATA_DIR / "logs"

STATE_DB_PATH = Path(
    _read_env("HUNTX_STATE_DB_PATH", "huntx_STATE_DB_PATH", str(STATE_DIR / "state.db"))
).resolve()


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

    # Update env vars for both current and legacy spellings.
    # Keep legacy keys for backward compatibility with older scripts.
    resolved_db = str(Path(db_path).resolve())
    os.environ["HUNTX_DATA_DIR"] = str(d)
    os.environ["huntx_DATA_DIR"] = str(d)
    os.environ["HUNTX_STATE_DB_PATH"] = resolved_db
    os.environ["huntx_STATE_DB_PATH"] = resolved_db

    DATA_DIR = d
    RAW_STORE_DIR = DATA_DIR / "raw"
    ARTIFACT_STORE_DIR = DATA_DIR / "artifacts"
    REJECTS_DIR = DATA_DIR / "rejects"
    STATE_DIR = DATA_DIR / "state"
    LOGS_DIR = DATA_DIR / "logs"

    STATE_DB_PATH = Path(resolved_db).resolve()
