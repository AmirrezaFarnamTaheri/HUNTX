import yaml
import logging
from pathlib import Path
from .schema import AppConfig

logger = logging.getLogger(__name__)

def load_config(path: str) -> AppConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(p, "r") as f:
        data = yaml.safe_load(f)

    # Use Pydantic model_validate (v2) or parse_obj (v1)
    # We installed Pydantic v2
    try:
        config = AppConfig.model_validate(data)
        logger.info(f"Loaded config with {len(config.sources)} sources and {len(config.routes)} routes.")
        return config
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise
