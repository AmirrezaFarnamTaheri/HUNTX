from __future__ import annotations

import getpass
import hashlib
import logging
import math
import os
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..config.loader import load_config
from ..config.schema import AppConfig
from ..config.validate import validate_config
from ..core.locks import acquire_lock
from ..core.run_health import RunHealth, emit_run_health, evaluate_run_health
from ..core.runtime_factory import create_production_orchestrator
from ..store import paths
from ..utils.env import env_bool, env_int
from ..utils.safe_names import safe_component

logger = logging.getLogger(__name__)

_DEFAULT_RUN_TIMEOUT_SECONDS = 12_600.0
_MAX_WORKERS = 64
_FETCH_WINDOW_KEYS = frozenset(
    {
        "msg_fresh_hours",
        "file_fresh_hours",
        "msg_subsequent_hours",
        "file_subsequent_hours",
    }
)


@dataclass(frozen=True)
class RunExecution:
    """Result of one governed HUNTX runtime invocation."""

    summary: dict[str, Any]
    health: RunHealth


def _resolve_run_timeout(value: float | str | None = None) -> float:
    """Return a finite positive runtime timeout, failing soft for environment input."""

    supplied_explicitly = value is not None
    raw: float | str = (
        value
        if value is not None
        else os.getenv("HUNTX_RUN_TIMEOUT", str(int(_DEFAULT_RUN_TIMEOUT_SECONDS)))
    )
    try:
        parsed = float(raw)
    except (TypeError, ValueError) as exc:
        if supplied_explicitly:
            raise ValueError(f"run timeout must be numeric, got {raw!r}") from exc
        logger.warning(
            "Invalid HUNTX_RUN_TIMEOUT=%r; using %.0f seconds",
            raw,
            _DEFAULT_RUN_TIMEOUT_SECONDS,
        )
        return _DEFAULT_RUN_TIMEOUT_SECONDS

    if not math.isfinite(parsed) or parsed <= 0:
        if supplied_explicitly:
            raise ValueError("run timeout must be finite and greater than zero")
        logger.warning(
            "Invalid HUNTX_RUN_TIMEOUT=%r; using %.0f seconds",
            raw,
            _DEFAULT_RUN_TIMEOUT_SECONDS,
        )
        return _DEFAULT_RUN_TIMEOUT_SECONDS
    return parsed


def _resolve_max_workers(value: int | None = None) -> int:
    """Resolve a bounded worker count for CLI and embedded runtime entrypoints."""

    if value is None:
        return env_int("HUNTX_MAX_WORKERS", 3, min_value=1, max_value=_MAX_WORKERS)
    if isinstance(value, bool):
        raise ValueError("max_workers must be an integer")
    try:
        workers = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"max_workers must be an integer, got {value!r}") from exc
    if workers != value or workers < 1 or workers > _MAX_WORKERS:
        raise ValueError(f"max_workers must be between 1 and {_MAX_WORKERS}")
    return workers


def _normalize_fetch_windows(
    fetch_windows: Mapping[str, Any] | None,
) -> dict[str, float] | None:
    """Validate explicit CLI lookback windows before they reach connectors."""

    if fetch_windows is None:
        return None
    unknown = set(fetch_windows) - _FETCH_WINDOW_KEYS
    if unknown:
        raise ValueError(f"Unknown fetch-window setting(s): {', '.join(sorted(unknown))}")

    normalized: dict[str, float] = {}
    for key in _FETCH_WINDOW_KEYS:
        if key not in fetch_windows:
            continue
        raw = fetch_windows[key]
        if isinstance(raw, bool):
            raise ValueError(f"{key} must be numeric, got {raw!r}")
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric, got {raw!r}") from exc
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{key} must be finite and non-negative")
        normalized[key] = value
    return normalized


def _configured_session_identities(config: AppConfig) -> tuple[str, ...]:
    """Return every configured MTProto session identity in deterministic order."""

    identities = {
        str(source.telegram_user.session).strip()
        for source in config.sources
        if source.type == "telegram_user"
        and source.telegram_user is not None
        and source.telegram_user.session
        and str(source.telegram_user.session).strip()
    }
    return tuple(sorted(identities))


def _session_lock_root() -> Path:
    """Return a per-host/user lock namespace independent of runtime data paths."""
    configured = os.getenv("HUNTX_SESSION_LOCK_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    if hasattr(os, "getuid"):
        principal = str(os.getuid())
    else:  # Windows has no os.getuid().
        principal = safe_component(getpass.getuser(), default="user", max_len=64)
    return Path(tempfile.gettempdir()) / f"huntx-session-locks-{principal}"


def _process_session_lock_path(root: Path, session_identity: str) -> Path:
    """Return an OS-lock path distinct from durable session-lease files.

    ``core.session_lease`` owns ``session-leases/*.lock`` using file existence,
    heartbeat, and stale-reaping semantics. Operator process fencing uses OS
    advisory locks instead, so it must never reuse that pathname protocol.
    """
    digest = hashlib.sha256(session_identity.encode("utf-8")).hexdigest()[:24]
    return root / "process-locks" / f"{digest}.lock"


def execute_pipeline_run(
    config_path: str | Path,
    *,
    fetch_windows: Mapping[str, Any] | None = None,
    no_publish: bool = False,
    max_workers: int | None = None,
    timeout: float | str | None = None,
    allow_partial_export: bool | None = None,
    health_logger: logging.Logger | None = None,
) -> RunExecution:
    """Execute the single governed production run contract.

    This is the shared boundary for command-line, compatibility helper, and
    embedded operator entrypoints. It prevents callers from accidentally
    constructing the legacy ``Orchestrator`` and bypassing persistent-window
    ingestion, source governance, governed builds, output ownership, consumer
    reconciliation, or runtime resilience.
    """

    config = load_config(config_path)
    validate_config(config)

    workers = _resolve_max_workers(max_workers)
    run_timeout = _resolve_run_timeout(timeout)
    windows = _normalize_fetch_windows(fetch_windows)
    partial_export = (
        env_bool("HUNTX_ALLOW_PARTIAL_EXPORT", True)
        if allow_partial_export is None
        else bool(allow_partial_export)
    )

    # One state lock serializes mutation of this runtime's durable state. A
    # separate host/user-global namespace fences every configured Telethon
    # session identity even when two invocations intentionally use different
    # data directories. Locks are acquired in sorted identity order to avoid
    # deadlocks in multi-session configurations.
    with ExitStack() as stack:
        stack.enter_context(acquire_lock(Path(paths.STATE_DIR) / "huntx.lock"))
        session_root = _session_lock_root()
        for identity in _configured_session_identities(config):
            stack.enter_context(
                acquire_lock(_process_session_lock_path(session_root, identity))
            )

        orchestrator = create_production_orchestrator(
            config,
            max_workers=workers,
            fetch_windows=windows,
        )
        summary = orchestrator.run(
            timeout=run_timeout,
            no_publish=bool(no_publish),
            allow_partial_export=partial_export,
        )

    health = evaluate_run_health(summary, no_publish=bool(no_publish))
    emit_run_health(
        summary,
        health,
        logger=health_logger or logger,
    )
    return RunExecution(summary=dict(summary), health=health)


def emit_unhandled_failure(
    exc: BaseException,
    *,
    no_publish: bool,
    health_logger: logging.Logger | None = None,
) -> RunExecution:
    """Persist a minimal structured fatal envelope for a failed entrypoint."""

    summary: dict[str, Any] = {
        "status": "failed",
        "reason": "unhandled_exception",
        "exception_type": type(exc).__name__,
        "total_artifacts": 0,
        "ingest_ok": 0,
        "ingest_err": 0,
    }
    health = evaluate_run_health(summary, no_publish=bool(no_publish))
    emit_run_health(summary, health, logger=health_logger or logger)
    return RunExecution(summary=summary, health=health)
