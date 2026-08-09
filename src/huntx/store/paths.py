import os
from dataclasses import dataclass
from pathlib import Path

# Base directory for all data
# Can be overridden by env var HUNTX_DATA_DIR
DATA_DIR = Path(os.getenv("HUNTX_DATA_DIR", "data")).resolve()

# Specific subdirectories
RAW_STORE_DIR = DATA_DIR / "raw"
ARTIFACT_STORE_DIR = DATA_DIR / "artifacts"
REJECTS_DIR = DATA_DIR / "rejects"
STATE_DIR = DATA_DIR / "state"
LOGS_DIR = DATA_DIR / "logs"

# Generated outputs (published artifacts)
# Usually committed to repo or uploaded to Releases
OUTPUT_DIR = DATA_DIR / "outputs"
DEV_OUTPUT_DIR = DATA_DIR / "outputs_dev"

STATE_DB_PATH = Path(os.getenv("HUNTX_STATE_DB_PATH", str(STATE_DIR / "state.db"))).resolve()


@dataclass(frozen=True)
class RuntimePaths:
    data_dir: Path
    raw_store_dir: Path
    artifact_store_dir: Path
    rejects_dir: Path
    state_dir: Path
    logs_dir: Path
    output_dir: Path
    dev_output_dir: Path
    state_db_path: Path


def current_paths() -> RuntimePaths:
    """Capture an immutable path set for one runtime instance."""
    return RuntimePaths(
        data_dir=DATA_DIR,
        raw_store_dir=RAW_STORE_DIR,
        artifact_store_dir=ARTIFACT_STORE_DIR,
        rejects_dir=REJECTS_DIR,
        state_dir=STATE_DIR,
        logs_dir=LOGS_DIR,
        output_dir=OUTPUT_DIR,
        dev_output_dir=DEV_OUTPUT_DIR,
        state_db_path=STATE_DB_PATH,
    )


def ensure_dirs():
    """Create all necessary directories."""
    for d in [
        DATA_DIR,
        RAW_STORE_DIR,
        ARTIFACT_STORE_DIR,
        REJECTS_DIR,
        STATE_DIR,
        LOGS_DIR,
        OUTPUT_DIR,
        DEV_OUTPUT_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)


def set_paths(data_dir: str, db_path: str):
    """
    Sets the global path variables and environment variables.

    Args:
        data_dir: The base data directory.
        db_path: The path to the state database file.
    """
    global DATA_DIR, RAW_STORE_DIR, ARTIFACT_STORE_DIR, REJECTS_DIR, STATE_DIR, LOGS_DIR, STATE_DB_PATH, OUTPUT_DIR, DEV_OUTPUT_DIR

    d = Path(data_dir).resolve()

    # Update env vars.
    resolved_db = str(Path(db_path).resolve())
    os.environ["HUNTX_DATA_DIR"] = str(d)
    os.environ["HUNTX_STATE_DB_PATH"] = resolved_db

    DATA_DIR = d
    RAW_STORE_DIR = DATA_DIR / "raw"
    ARTIFACT_STORE_DIR = DATA_DIR / "artifacts"
    REJECTS_DIR = DATA_DIR / "rejects"
    STATE_DIR = DATA_DIR / "state"
    LOGS_DIR = DATA_DIR / "logs"
    OUTPUT_DIR = DATA_DIR / "outputs"
    DEV_OUTPUT_DIR = DATA_DIR / "outputs_dev"

    STATE_DB_PATH = Path(resolved_db).resolve()
