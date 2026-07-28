from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, Mapping, Optional, Type


def _validate_fingerprint(token_fingerprint: str) -> None:
    if len(token_fingerprint) != 64 or any(
        char not in "0123456789abcdef" for char in token_fingerprint
    ):
        raise ValueError("token_fingerprint must be a lowercase SHA-256 digest")


def _normalize_consumer_id(consumer_id: str) -> str:
    normalized = str(consumer_id).strip()
    if not normalized:
        raise ValueError("consumer_id is required")
    if len(normalized) > 512:
        raise ValueError("consumer_id is too long")
    return normalized
