#!/usr/bin/env python3
"""Check MTProto evidence without making Telegram availability a release dependency.

Only malformed or contradictory diagnostics fail this observability workflow.
A disconnected, rate-limited, or empty Telegram source is a *degraded signal*,
never evidence of a broken build or a successful Telegram ingestion.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping


class EvidenceContractError(ValueError):
    """Malformed or impossible provenance; not an upstream availability error."""


_LIFO_COMPLETE = re.compile(
    r"\[LIFO\]\s+source=(\S+).*?\bscanned=(\d+)\s+"
    r"ingested=(\d+).*?\bcompleted=True"
)
_FLOOD_WAIT = re.compile(r"\[LIFO\].*?preflight rate-limited for (\d+)s")


def _nonnegative_int(summary: Mapping[str, Any], key: str) -> int:
    value = summary.get(key)
    if type(value) is not int:
        raise EvidenceContractError(f"{key} must be an integer, got {value!r}")
    if value < 0:
        raise EvidenceContractError(f"{key} must be non-negative, got {value}")
    return value


def evaluate(
    runtime_log: str,
    run_payload: Mapping[str, Any],
    *,
    source_run_id: int,
    source_health: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a neutral/degraded/verified verdict without inventing proxy health.

    Runtime source counters include HTTP checks. They are never assumed to
    prove that Telegram completed scanning. Only completed window lines plus
    consistent aggregate metrics can establish verified Telegram activity.
    """
    if type(source_run_id) is not int or source_run_id <= 0:
        raise EvidenceContractError("source_run_id must be a positive integer")
    if not isinstance(run_payload, Mapping) or type(run_payload.get("schema_version")) is not int or run_payload["schema_version"] != 1:
        raise EvidenceContractError("run-summary.json requires schema_version=1")
    summary = run_payload.get("summary")
    if not isinstance(summary, Mapping):
        raise EvidenceContractError("run-summary.json requires a structured summary object")
    sources_checked = _nonnegative_int(summary, "sources_checked")
    messages_scanned = _nonnegative_int(summary, "messages_scanned")
    windows_completed = _nonnegative_int(summary, "lifo_windows_completed")
    # Runtime summaries use the nested LIFO residue contract; older fixtures
    # may carry the same total at the top level.
    if "lifo_residue_remaining" in summary:
        windows_pending = _nonnegative_int(summary, "lifo_residue_remaining")
    else:
        residue = summary.get("lifo_residue")
        if not isinstance(residue, Mapping):
            raise EvidenceContractError("lifo_residue requires a remaining window count")
        windows_pending = _nonnegative_int(residue, "remaining")

    telegram_enabled: int | None = None
    telegram_statuses: dict[str, int] = {}
    if source_health is not None:
        if (not isinstance(source_health, Mapping)
                or type(source_health.get("schema_version")) is not int
                or source_health["schema_version"] != 1
                or not isinstance(source_health.get("sources"), list)):
            raise EvidenceContractError("source-health.json requires a sources list and schema_version=1")
        telegram = []
        for source in source_health["sources"]:
            if not isinstance(source, Mapping):
                raise EvidenceContractError("source-health.json contains a non-object source")
            if source.get("type") == "telegram_user" and source.get("enabled") is True:
                telegram.append(source)
        telegram_enabled = len(telegram)
        for source in telegram:
            name = str(source.get("status") or "unknown")
            telegram_statuses[name] = telegram_statuses.get(name, 0) + 1

    lines = runtime_log.splitlines()
    connections = sum("[MTProto] Connected." in line for line in lines)
    resolutions = sum("[MTProto] Resolved peer " in line for line in lines)
    unavailable = sum("permanently unavailable Telegram source=" in line for line in lines)
    completed = [
        (match.group(1), int(match.group(2)), int(match.group(3)))
        for line in lines if (match := _LIFO_COMPLETE.search(line))
    ]
    scanned_in_log = sum(item[1] for item in completed)
    ingested_in_log = sum(item[2] for item in completed)
    observed_sources = len({item[0] for item in completed})
    waits = [int(match.group(1)) for line in lines if (match := _FLOOD_WAIT.search(line))]

    if len(completed) > windows_completed:
        raise EvidenceContractError(
            f"Completed-window log count exceeds structured total: {len(completed)} > {windows_completed}"
        )
    if scanned_in_log > messages_scanned:
        raise EvidenceContractError(
            f"Completed-window scan evidence exceeds structured total: {scanned_in_log} > {messages_scanned}"
        )
    if observed_sources > sources_checked:
        raise EvidenceContractError(
            f"Distinct completed sources exceed structured count: {observed_sources} > {sources_checked}"
        )
    if ingested_in_log > scanned_in_log:
        raise EvidenceContractError("Completed window ingested count exceeds scanned count")
    if telegram_enabled == 0 and (len(completed) or windows_completed or messages_scanned):
        raise EvidenceContractError("Completed Telegram activity contradicts zero configured Telegram sources")

    verified = bool(completed and scanned_in_log > 0 and connections and resolutions)
    if verified:
        status = "verified_activity"
    elif completed and scanned_in_log == 0 and windows_completed == len(completed) and messages_scanned == 0:
        status = "completed_empty"
    elif windows_completed > len(completed) or messages_scanned > scanned_in_log:
        status = "inconclusive"
    elif telegram_enabled == 0:
        status = "not_configured"
    elif waits:
        status = "rate_limited"
    elif not connections or not resolutions:
        status = "unavailable"
    else:
        status = "no_observed_ingestion"

    return {
        "schema_version": 1,
        "source_run_id": source_run_id,
        "status": status,
        "verified_telegram_ingestion": verified,
        "availability_nonblocking": True,
        "mtproto_connections": connections,
        "mtproto_peers_resolved": resolutions,
        "telegram_sources_enabled": telegram_enabled,
        "telegram_source_statuses": telegram_statuses,
        "telegram_sources_observed": observed_sources,
        "completed_source_windows": len(completed),
        "completed_window_messages_scanned": scanned_in_log,
        "completed_window_messages_ingested": ingested_in_log,
        "run_summary_sources_checked": sources_checked,
        "run_summary_messages_scanned": messages_scanned,
        "run_summary_windows_completed": windows_completed,
        "run_summary_windows_pending": windows_pending,
        "permanently_unavailable_source_events": unavailable,
        "retry_delay_seconds": max(waits) if waits else 0,
    }


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise EvidenceContractError(f"Cannot decode evidence file {path.name}: {exc}") from exc
    if not isinstance(result, dict):
        raise EvidenceContractError(f"Evidence file {path.name} must be an object")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-log", type=Path, required=True)
    parser.add_argument("--run-summary", type=Path, required=True)
    parser.add_argument("--source-health", type=Path)
    parser.add_argument("--source-run-id", type=int, required=True)
    parser.add_argument("--output", type=Path, default=Path("telegram-activity-evidence.json"))
    args = parser.parse_args()
    try:
        runtime_log = args.runtime_log.read_text(encoding="utf-8", errors="replace")
        if not runtime_log.strip():
            raise EvidenceContractError("runtime.log is empty")
        evidence = evaluate(
            runtime_log,
            _load_json(args.run_summary),
            source_run_id=args.source_run_id,
            source_health=_load_json(args.source_health) if args.source_health is not None else None,
        )
        args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("Telegram evidence disposition:", evidence["status"])
        if not evidence["verified_telegram_ingestion"]:
            print(
                "::warning title=Telegram ingestion not verified::"
                f"Status={evidence['status']}; this source-availability condition does not fail production. "
                "No Telegram ingestion success or authenticated proxy health is inferred."
            )
        return 0
    except (EvidenceContractError, OSError) as exc:
        print(f"::error title=Invalid Telegram diagnostics::{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
