"""Typed, fail-soft readers for environment-supplied configuration.

Environment variables are operator input and frequently wrong (a typo, an
unexpanded ``${...}`` placeholder, an empty value from a CI template). A bare
``int(os.environ.get(NAME, "0"))`` turns any of those into an uncaught
``ValueError`` at an arbitrary point in the run — often *after* expensive work
has completed. These helpers centralize the "parse, validate, warn, fall back"
pattern that was previously duplicated (and inconsistently applied) across the
CLI, bot delivery, format bundling, and publisher modules.

Note the deliberate contrast with :mod:`huntx.config.env_expand`: a *required*
``${VAR}`` reference in the YAML config must fail loudly, because it is an
explicit assertion that the value is mandatory. The knobs read here are tuning
parameters with meaningful defaults, so degrading to the default with a warning
is the correct behavior rather than aborting the run.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def env_int(
    name: str,
    default: int,
    *,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> int:
    """Read an integer from the environment, falling back to ``default``.

    Falls back (with a warning) when the variable is unset, empty, not an
    integer, or outside ``[min_value, max_value]``. Never raises, so callers
    can treat the result as always usable.

    Args:
        name: Environment variable to read.
        default: Value used when the variable is absent or unusable. Assumed to
            already satisfy any bounds given.
        min_value: Inclusive lower bound; values below it fall back to default.
        max_value: Inclusive upper bound; values above it fall back to default.

    Returns:
        The parsed, in-range integer, or ``default``.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r (expected an integer); using %d.", name, raw, default)
        return default

    if min_value is not None and value < min_value:
        logger.warning("%s=%d is below the minimum of %d; using %d.", name, value, min_value, default)
        return default
    if max_value is not None and value > max_value:
        logger.warning("%s=%d exceeds the maximum of %d; using %d.", name, value, max_value, default)
        return default

    return value


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean from the environment, falling back to ``default``.

    Accepts the spellings already used across this codebase and its CI
    (``1``/``0``, ``true``/``false``, ``yes``/``no``, ``on``/``off``), case
    insensitively. An unrecognized value warns and falls back rather than
    silently reading as false, which would quietly disable a flag the operator
    believed they had set.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    token = raw.strip().lower()
    if token in ("1", "true", "yes", "on"):
        return True
    if token in ("0", "false", "no", "off"):
        return False

    logger.warning("Invalid %s=%r (expected a boolean); using %s.", name, raw, default)
    return default
