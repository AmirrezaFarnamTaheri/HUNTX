import os
import re
from typing import Any

# ``${VAR}`` (required) or ``${VAR:-default}`` (optional with fallback).
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}")


def expand_env(text: str) -> str:
    """Expand ``${VAR}`` / ``${VAR:-default}`` references in ``text``.

    Resolution order for each reference:

    1. If the environment variable is set, its value is substituted.
    2. Otherwise, if a ``:-default`` fallback is supplied (even an empty one,
       ``${VAR:-}``), the default is substituted.
    3. Otherwise the reference is *required* but unset, and a
       :class:`ValueError` is raised.

    Rationale: a bare ``${VAR}`` is an explicit assertion that the value is
    mandatory. Silently substituting an empty string there masks
    misconfiguration (e.g. a production deploy missing ``TELEGRAM_API_HASH``)
    and defers the failure to a far less obvious point. Callers that genuinely
    want an optional value must opt in with the ``${VAR:-}`` fallback syntax.
    """

    def replace(m: "re.Match[str]") -> str:
        var_name = m.group(1)
        default_val = m.group(2)
        val = os.getenv(var_name)
        if val is not None:
            return val
        if default_val is not None:
            return default_val
        raise ValueError(f"Missing required environment variable: {var_name}")

    return _ENV_PATTERN.sub(replace, text)


def recursive_expand(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: recursive_expand(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [recursive_expand(item) for item in data]
    elif isinstance(data, str):
        return expand_env(data)
    else:
        return data
