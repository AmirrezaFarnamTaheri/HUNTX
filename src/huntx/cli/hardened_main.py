import os
import sys
from pathlib import Path
from typing import Any, Sequence

from . import main as cli


def _option_value(argv: Sequence[str], option: str) -> str | None:
    for index, value in enumerate(argv[1:], start=1):
        if value == option:
            if index + 1 < len(argv):
                return argv[index + 1]
            return None
        prefix = option + "="
        if value.startswith(prefix):
            return value[len(prefix) :]
    return None


def _has_option(argv: Sequence[str], option: str) -> bool:
    return any(value == option or value.startswith(option + "=") for value in argv[1:])


def _inject_runtime_path_arguments(argv: Sequence[str]) -> list[str]:
    """Apply CLI > environment > default precedence for runtime paths."""

    resolved = list(argv)
    explicit_data = _option_value(resolved, "--data-dir")
    data_dir = explicit_data or os.environ.get("HUNTX_DATA_DIR") or "data"

    additions: list[str] = []
    if not _has_option(resolved, "--data-dir"):
        additions.extend(["--data-dir", data_dir])
    if not _has_option(resolved, "--db-path"):
        db_path = os.environ.get("HUNTX_STATE_DB_PATH") or str(
            Path(data_dir) / "state" / "state.db"
        )
        additions.extend(["--db-path", db_path])
    return [resolved[0], *additions, *resolved[1:]]


def _all_publish_failures_are_fatal(
    summary: dict[str, Any],
    *,
    no_publish: bool,
) -> bool:
    """Compatibility shim: publication failures remain degraded, not fatal."""
    del summary, no_publish
    return False


def main() -> None:
    """Compatibility console entrypoint with environment-aware path defaults.

    Runtime execution itself lives in :mod:`huntx.cli.run_service` and is used
    by ``huntx.cli.main`` directly. Keeping this wrapper avoids breaking the
    installed ``huntx`` console script while eliminating the previous
    import-time monkey patch that made runtime behavior depend on entrypoint.
    """

    sys.argv = _inject_runtime_path_arguments(sys.argv)
    cli.main()


if __name__ == "__main__":
    main()
