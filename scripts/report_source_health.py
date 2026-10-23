"""Produce a credential-free inventory of per-source ingestion evidence.

HTTP status describes feed retrieval/parsing, not a functional proxy check.
Telegram status describes campaign windows, not public endpoint reachability.
Never emit raw URLs, headers, Telegram sessions or upstream error messages.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

_WINDOW_STATUSES = frozenset({"completed", "retry_wait", "partial", "leased", "pending", "quarantined"})
_AVAILABILITY_FIELDS = (
    "kind", "successes", "failures", "consecutive_failures", "rolling_samples",
    "rolling_successes", "rolling_success_rate", "rolling_wilson_lower_bound",
    "wilson_lower_bound", "cache_revalidations", "ranking_score",
    "last_success_at", "last_failed_at", "success_age_seconds", "freshness",
    "evidence",
)
_HTTP_FIELDS = (
    "nodes", "profiles", "policy_bound", "skipped_incompatible", "checked_at",
    "last_changed_at", "revalidated", "validation",
)
_ERROR_TYPE = re.compile(r"^[A-Za-z_][A-Za-z_0-9]{0,63}$")


def load_queue_evidence(db_path: Path, campaign_id: object) -> dict[str, dict[str, int]] | None:
    """Aggregate only the active campaign, not lifetime work items."""
    if type(campaign_id) is not int or campaign_id <= 0 or not db_path.is_file():
        return None
    uri = "file:" + quote(str(db_path.resolve()), safe="/") + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=10) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT source_id, status, COUNT(*) AS total, "
                "COALESCE(SUM(items_ingested),0) AS items, MAX(updated_at) AS updated "
                "FROM ingestion_work_items WHERE campaign_id = ? "
                "GROUP BY source_id, status", (campaign_id,),
            ).fetchall()
    except (sqlite3.Error, OSError):
        return None
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        source_id = str(row["source_id"])
        status = str(row["status"])
        if status not in _WINDOW_STATUSES:
            continue
        item = result.setdefault(source_id, {"items_ingested": 0, "updated_at": 0})
        item[status] = item.get(status, 0) + max(0, int(row["total"]))
        item["items_ingested"] += max(0, int(row["items"]))
        item["updated_at"] = max(item["updated_at"], int(row["updated"] or 0))
    return result


def _http_evidence(report: Mapping[str, Any]) -> dict[str, Any]:
    evidence = {
        key: report[key] for key in _HTTP_FIELDS if key in report
        and isinstance(report[key], (str, int, float, bool, type(None)))
    }
    availability = report.get("availability")
    if isinstance(availability, Mapping):
        evidence["availability"] = {
            key: availability[key] for key in _AVAILABILITY_FIELDS
            if key in availability and isinstance(
                availability[key], (str, int, float, type(None))
            )
        }
    error = report.get("error_type")
    if isinstance(error, str) and _ERROR_TYPE.fullmatch(error):
        evidence["error_type"] = error
    return evidence


def build_snapshot(
    configured: list[dict[str, Any]],
    health_report: Mapping[str, Any],
    queue_evidence: Mapping[str, Mapping[str, int]] | None,
    *,
    observed_at: int,
    run_id: str = "",
) -> dict[str, Any]:
    """Classify observations explicitly, including disabled and unobserved sources."""
    envelope = health_report.get("summary", {})
    summary = envelope if isinstance(envelope, Mapping) else {}
    reported = summary.get("http_source_health", {})
    http_reports = reported if isinstance(reported, Mapping) else {}
    counts = {
        "configured_sources": 0, "enabled": 0, "disabled": 0,
        "http_retrieved": 0, "http_source_failures": 0,
        "http_infrastructure_errors": 0, "http_not_observed": 0,
        "telegram_observed": 0, "telegram_retrying": 0,
        "telegram_quarantined": 0, "telegram_not_observed": 0,
        "evidence_unavailable": 0,
    }
    ids: set[str] = set()
    sources: list[dict[str, Any]] = []
    for source in configured:
        if not isinstance(source, dict) or not isinstance(source.get("id"), str) or not source["id"]:
            raise ValueError("source inventory entries must have a nonempty id")
        source_id = source["id"]
        if source_id in ids:
            raise ValueError(f"duplicate source id {source_id}")
        ids.add(source_id)
        source_type = str(source.get("type", "unknown"))
        feed_cfg = source.get("http_subscription")
        enabled = (
            source.get("trust_state", "approved") == "approved" and
            (source_type != "http_subscription" or
             (isinstance(feed_cfg, dict) and feed_cfg.get("enabled", True) is True))
        )
        row: dict[str, Any] = {
            "id": source_id, "type": source_type, "enabled": enabled,
            "required": source.get("required", True) is True,
        }
        counts["configured_sources"] += 1
        if not enabled:
            row["status"] = "disabled"
            counts["disabled"] += 1
        else:
            counts["enabled"] += 1
            if source_type == "http_subscription":
                report = http_reports.get(source_id)
                valid_report = report if isinstance(report, Mapping) else {}
                status = valid_report.get("status")
                if status in {"parsed", "audited"}:
                    row["status"] = "retrieved"
                    counts["http_retrieved"] += 1
                elif status == "failed":
                    row["status"] = "source_failure"
                    counts["http_source_failures"] += 1
                elif status == "infrastructure_error":
                    row["status"] = "infrastructure_error"
                    counts["http_infrastructure_errors"] += 1
                else:
                    row["status"] = "not_observed"
                    counts["http_not_observed"] += 1
                if valid_report:
                    row["http"] = _http_evidence(valid_report)
            elif source_type == "telegram_user" and queue_evidence is not None:
                data = queue_evidence.get(source_id, {})
                windows = {k: max(0, int(data.get(k, 0))) for k in sorted(_WINDOW_STATUSES)}
                windows["items_ingested"] = max(0, int(data.get("items_ingested", 0)))
                windows["updated_at"] = max(0, int(data.get("updated_at", 0)))
                row["windows"] = windows
                if windows["quarantined"]:
                    row["status"] = "quarantined"
                    counts["telegram_quarantined"] += 1
                elif windows["retry_wait"]:
                    row["status"] = "retrying"
                    counts["telegram_retrying"] += 1
                elif windows["completed"]:
                    row["status"] = "observed"
                    counts["telegram_observed"] += 1
                else:
                    row["status"] = "not_observed"
                    counts["telegram_not_observed"] += 1
            elif source_type == "telegram_user":
                row["status"] = "evidence_unavailable"
                counts["evidence_unavailable"] += 1
            else:
                row["status"] = "not_observed"
        sources.append(row)
    return {
        "schema_version": 1,
        "source_observation_kind": "retrieval_and_ingestion_only_not_proxy_health",
        "observed_at": observed_at,
        "run_id": run_id,
        "queue_campaign_id": summary.get("lifo_campaign_id"),
        "queue_evidence_available": queue_evidence is not None,
        "counts": counts,
        "sources": sorted(sources, key=lambda row: row["id"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import yaml

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    health = json.loads(args.summary.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("sources"), list):
        raise ValueError("invalid source inventory")
    if not isinstance(health, dict) or not isinstance(health.get("summary"), dict):
        raise ValueError("missing structured runtime health summary")
    campaign_id = health["summary"].get("lifo_campaign_id")
    queue = load_queue_evidence(args.db, campaign_id)
    snapshot = build_snapshot(
        config["sources"], health, queue, observed_at=int(time.time()),
        run_id=os.environ.get("GITHUB_RUN_ID", ""),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    counts = snapshot["counts"]
    print("source-health: " + " ".join(f"{key}={value}" for key, value in counts.items()))
    if counts["http_infrastructure_errors"]:
        print(
            "::warning title=HTTP source infrastructure unavailable::"
            f"{counts['http_infrastructure_errors']} sources could not be tested; "
            "do not count them as dead feeds"
        )
    if counts["http_source_failures"]:
        print(
            "::warning title=HTTP source retrieval failed::"
            f"{counts['http_source_failures']} feeds failed retrieval/parsing checks"
        )
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with Path(step_summary).open("a", encoding="utf-8") as summary_file:
            summary_file.write(
                "\n### Per-source ingestion health\n\n"
                f"- Inventory: {counts['configured_sources']} configured; "
                f"{counts['enabled']} enabled; {counts['disabled']} disabled\n"
                f"- HTTP feeds: {counts['http_retrieved']} retrieved, "
                f"{counts['http_source_failures']} source failures, "
                f"{counts['http_infrastructure_errors']} infrastructure errors\n"
                f"- Telegram: {counts['telegram_observed']} observed, "
                f"{counts['telegram_retrying']} retrying, "
                f"{counts['telegram_quarantined']} quarantined\n"
                "- Evidence: source retrieval and ingestion only; "
                "not authenticated proxy health\n"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
