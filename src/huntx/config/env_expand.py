import os
import re
from typing import Any


def expand_env(text: str) -> str:
    # Match ${VAR} or ${VAR:-default}
    pattern = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")

    def replace(m: re.Match[str]) -> str:
        var_name = m.group(1)
        default_val = m.group(2)
        val = os.getenv(var_name)
        if val is not None:
            return val
        if default_val is not None:
            return default_val
        raise ValueError(f"Missing required environment variable: {var_name}")

    return pattern.sub(replace, text)


def recursive_expand(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: recursive_expand(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [recursive_expand(item) for item in data]
    elif isinstance(data, str):
        return expand_env(data)
    else:
        return data
