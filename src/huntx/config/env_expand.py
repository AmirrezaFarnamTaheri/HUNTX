import os
import re
from typing import Any


def expand_env(text: str) -> str:
    # Use raw string for regex
    pattern = re.compile(r"\$\{([A-Z0-9_]+)\}")
    return pattern.sub(lambda m: os.getenv(m.group(1), ""), text)


def recursive_expand(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: recursive_expand(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [recursive_expand(item) for item in data]
    elif isinstance(data, str):
        return expand_env(data)
    else:
        return data
