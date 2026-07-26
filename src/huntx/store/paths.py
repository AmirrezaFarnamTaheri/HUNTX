import os
from pathlib import Path

DATA_DIR = Path(os.getenv("HUNTX_DATA_DIR", "data")).resolve()
RAW_STORE_DIR = DATA_DIR / "raw"
ARTIFACT_STORE_DIR = DATA_DIR / "artifacts"
REJECTS_DIR = DATA_DIR / "rejects"
STATE_DIR = DATA_DIR / "state"
LOGS_DIR = DATA_DIR / "logs"
OUTPUT_DIR = DATA_DIR / "outputs"
DEV_OUTPUT_DIR = DATA_DIR / "outputs_dev"
STATE_DB_PATH = Path(os.getenv("HUNTX_STATE_DB_PATH", str(STATE_DIR / "state.db"))).resolve()


def ensure_dirs():
    """Create all necessary directories including custom DB parents."""
    db_parent = Path(STATE_DB_PATH).parent
    for directory in [
        DATA_DIR,
        RAW_STORE_DIR,
        ARTIFACT_STORE_DIR,
        REJECTS_DIR,
        STATE_DIR,
        db_parent,
        LOGS_DIR,
        OUTPUT_DIR,
        DEV_OUTPUT_DIR,
    ]:
        Path(directory).mkdir(parents=True, exist_ok=True)


def set_paths(data_dir: str, db_path: str):
    global DATA_DIR, RAW_STORE_DIR, ARTIFACT_STORE_DIR, REJECTS_DIR, STATE_DIR, LOGS_DIR, STATE_DB_PATH, OUTPUT_DIR, DEV_OUTPUT_DIR

    d = Path(data_dir).resolve()
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
