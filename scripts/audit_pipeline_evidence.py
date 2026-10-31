#!/usr/bin/env python3
"""Cross-check HUNTX diagnostics and score independently labeled pipeline samples.

Production telemetry cannot provide a true/false oracle for itself. TCP reachability,
repeated endpoint sightings, and successful serialization are not authenticated
proxy success. This tool reports *observed evidence* separately from measured
TP/TN/FP/FN. Only independently labeled samples can produce the latter.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

STAGES = (
    "source_registry", "telegram_ingestion", "http_ingestion", "feed_parsing",
    "canonicalization", "transformation", "semantic_deduplication",
    "endpoint_identity", "geo_attribution", "dns_diagnostics", "tcp_diagnostics",
    "tls_diagnostics", "proxy_authentication", "health_scoring", "client_exports",
    "release_eligibility", "publication", "frontend_delivery",
)


class AuditError(ValueError):
    """A contract inconsistency is not an external-source availability failure."""


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def score_labeled(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return actual confusion counts, excluding abstentions from scored support.

    A label must carry an oracle description. Supplying an oracle string does not
    prove independence; reviewers must verify its provenance separately.
    """
    if not isinstance(records, list):
        raise AuditError("labels must be a list")
    by_stage: dict[str, dict[str, Any]] = {}
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            raise AuditError(f"invalid labeled record at index {index}")
        stage = row.get("stage")
        identity = row.get("sample_id")
        oracle = row.get("oracle")
        prediction = row.get("predicted")
        truth = row.get("truth")
        if stage not in STAGES or not isinstance(identity, str) or not identity.strip():
            raise AuditError("unknown stage or invalid sample identity")
        if not isinstance(oracle, str) or not oracle.strip() or len(oracle) > 200:
            raise AuditError("independent ground-truth oracle/provenance is required")
        if type(truth) is not bool or (prediction is not None and type(prediction) is not bool):
            raise AuditError("truth must be Boolean and predicted must be Boolean or null")
        if (stage, identity) in seen:
            raise AuditError("duplicate labeled sample for the same stage")
        seen.add((stage, identity))
        counts = by_stage.setdefault(stage, {key: 0 for key in ("tp", "tn", "fp", "fn", "abstain")})
        if prediction is None:
            counts["abstain"] += 1
        elif prediction and truth:
            counts["tp"] += 1
        elif not prediction and not truth:
            counts["tn"] += 1
        elif prediction and not truth:
            counts["fp"] += 1
        else:
            counts["fn"] += 1

    results: dict[str, dict[str, Any]] = {}
    for stage in STAGES:
        counts = by_stage.get(stage)
        if counts is None:
            results[stage] = {"status": "unlabeled", "confusion_matrix": None}
            continue
        tp, tn, fp, fn = (counts[key] for key in ("tp", "tn", "fp", "fn"))
        results[stage] = {
            "status": "scored" if tp + tn + fp + fn else "all_abstained",
            **counts,
            "support": tp + tn + fp + fn,
            "ground_truth_count": tp + tn + fp + fn + counts["abstain"],
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
            "specificity": _ratio(tn, tn + fp),
            "fpr": _ratio(fp, fp + tn),
            "fnr": _ratio(fn, fn + tp),
            "npv": _ratio(tn, tn + fn),
            "accuracy": _ratio(tp + tn, tp + tn + fp + fn),
            "coverage": _ratio(tp + tn + fp + fn, tp + tn + fp + fn + counts["abstain"]),
        }
    return results


def _object(payload: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping) or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise AuditError(f"{label}: expected schema_version=1 object")
    return payload


def _count(record: Mapping[str, Any], key: str) -> int:
    value = record.get(key)
    if type(value) is not int or value < 0:
        raise AuditError(f"invalid nonnegative count: {key}")
    return value


def audit_artifacts(
    run_payload: Mapping[str, Any],
    source_health: Mapping[str, Any],
    endpoint_inventory: Mapping[str, Any],
    network_diagnostics: Mapping[str, Any],
    *,
    labels: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Inspect evidence coverage; do not infer unobserved client usability."""
    run = _object(run_payload, "run summary")
    src = _object(source_health, "source health")
    endpoint = _object(endpoint_inventory, "endpoint inventory")
    network = _object(network_diagnostics, "network diagnostics")
    summary, counts, ec, nc = (run.get("summary"), src.get("counts"),
                               endpoint.get("counts"), network.get("counts"))
    if not all(isinstance(item, Mapping) for item in (summary, counts, ec, nc)):
        raise AuditError("structured summary/counts missing from diagnostics")
    sources = src.get("sources")
    if not isinstance(sources, list) or not all(isinstance(item, Mapping) for item in sources):
        raise AuditError("source-health must enumerate source objects")
    enabled = sum(item.get("enabled") is True for item in sources)
    disabled = sum(item.get("enabled") is False for item in sources)
    if enabled != _count(counts, "enabled") or disabled != _count(counts, "disabled"):
        raise AuditError("source-health enabled sources / disabled sources mismatch")
    if enabled + disabled != _count(counts, "configured_sources"):
        raise AuditError("configured source count contradicts source registry")

    http_sources = [item for item in sources if item.get("type") == "http_subscription" and item.get("enabled") is True]
    telegram_sources = [item for item in sources if item.get("type") == "telegram_user" and item.get("enabled") is True]
    http_retrieved = _count(counts, "http_retrieved")
    http_failed = _count(counts, "http_source_failures")
    http_infrastructure = _count(counts, "http_infrastructure_errors")
    http_not_observed = _count(counts, "http_not_observed")
    if len(http_sources) != http_retrieved + http_failed + http_infrastructure + http_not_observed:
        raise AuditError("HTTP source health classifications do not cover enabled feeds")
    retrying = _count(counts, "telegram_retrying")
    telegram_observed = _count(counts, "telegram_observed")
    telegram_unobserved = _count(counts, "telegram_not_observed")
    telegram_quarantined = _count(counts, "telegram_quarantined")
    if len(telegram_sources) != retrying + telegram_observed + telegram_unobserved + telegram_quarantined:
        raise AuditError("Telegram source classifications do not cover enabled channels")

    distinct = _count(ec, "distinct_endpoint_ids")
    invalid = _count(ec, "invalid_records")
    scanned = _count(ec, "records_scanned")
    repeated = _count(ec, "duplicate_endpoint_observations")
    if distinct + repeated + invalid != scanned:
        raise AuditError("network endpoint identity reconciliation mismatch")
    if any(_count(ec, field) > distinct for field in ("unresolved_geo", "unattributed_asn")):
        raise AuditError("unattributed endpoints exceed distinct endpoint count")
    tested = _count(nc, "tested")
    candidates = _count(nc, "candidates")
    if tested > candidates:
        raise AuditError("tested endpoints exceed discovered candidates")
    layers = network.get("layers", {})
    if not isinstance(layers, Mapping):
        raise AuditError("network layer evidence must be an object")
    for name, outcomes in layers.items():
        if isinstance(outcomes, Mapping) and sum(_count(outcomes, k) for k in outcomes) != tested:
            raise AuditError(f"network layer {name} counts contradict tested sample")

    def item(verdict: str, **observed: Any) -> dict[str, Any]:
        return {"verdict": verdict, "observed": observed}

    stage = {name: item("unknown") for name in STAGES}
    stage["source_registry"] = item("observed", configured=enabled + disabled, enabled=enabled, disabled=disabled)
    telegram_scans = _count(summary, "messages_scanned")
    telegram_windows = _count(summary, "lifo_windows_completed")
    stage["telegram_ingestion"] = item(
        "degraded" if retrying and not telegram_windows else "observed" if telegram_windows else "unknown",
        sources=len(telegram_sources), retrying=retrying, completed_windows=telegram_windows,
        scanned_messages=telegram_scans,
    )
    stage["http_ingestion"] = item(
        "degraded" if http_failed or http_infrastructure or http_not_observed else "observed",
        sources=len(http_sources), retrieved=http_retrieved, source_failures=http_failed,
        infrastructure_failures=http_infrastructure, unobserved=http_not_observed,
        raw_nodes_observed=summary.get("http_nodes_observed"),
    )
    stage["feed_parsing"] = item("observed", retrieved_feeds=http_retrieved, rejected_feeds=http_failed,
                                 note="feed syntax does not establish working proxy authentication")
    transformation = summary.get("transform", {})
    if isinstance(transformation, Mapping):
        stage["transformation"] = item("observed" if transformation.get("completed") is True else "unknown",
                                       processed=transformation.get("processed"), records=transformation.get("records"))
    stage["endpoint_identity"] = item("observed", distinct=distinct, repeated_endpoint_observations=repeated,
                                      scanned=scanned, invalid=invalid)
    stage["geo_attribution"] = item("unknown" if _count(ec, "unresolved_geo") == distinct else "partial",
                                     unresolved_country=_count(ec, "unresolved_geo"),
                                     unattributed_asn=_count(ec, "unattributed_asn"), distinct=distinct,
                                     scope="network metadata, not physical exit geography")
    stage["dns_diagnostics"] = item("observed" if tested else "unknown",
                                    sampled=tested, outcomes=layers.get("dns"))
    stage["tcp_diagnostics"] = item("observed" if tested else "unknown",
                                    sampled=tested, outcomes=layers.get("tcp"),
                                    note="TCP connected is not authenticated proxy success")
    stage["tls_diagnostics"] = item("observed" if tested else "unknown",
                                    sampled=tested, outcomes=layers.get("tls"))
    auth = layers.get("proxy_protocol", {})
    verified_auth = _count(auth, "verified") if isinstance(auth, Mapping) and "verified" in auth else 0
    stage["proxy_authentication"] = item("observed" if verified_auth else "unknown",
                                         verified_in_diagnostic_sample=verified_auth,
                                         sample_size=tested, unverified=auth.get("unverified") if isinstance(auth, Mapping) else None)
    release = summary.get("release_eligible") is True
    stage["client_exports"] = item("unknown" if not release else "partial",
                                   built_artifacts=summary.get("total_artifacts"),
                                   note="build artifacts do not prove client import compatibility")
    stage["release_eligibility"] = item("observed" if release else "blocked",
                                        release_eligible=release, status=summary.get("status"))
    stage["publication"] = item("unknown" if release else "skipped",
                                note="a publisher receipt is required to verify actual deployment")
    result: dict[str, Any] = {
        "schema_version": 1,
        "assessment_scope": "structured_observations_not_independent_ground_truth",
        "confusion_matrix_status": "no_independent_labels" if labels is None else "independently_labeled_samples_supplied",
        "stages": stage,
        "integrity_checked": True,
    }
    if labels is not None:
        result["labeled_metrics"] = score_labeled(labels)
    return result


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise AuditError(f"missing or invalid JSON artifact: {path.name}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("summary", "source-health", "endpoint-inventory", "network-diagnostics"):
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--labels", type=Path, help="Separately verified sample oracle labels")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_artifacts(
            _read(args.summary), _read(args.source_health),
            _read(args.endpoint_inventory), _read(args.network_diagnostics),
            labels=_read(args.labels) if args.labels else None,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("pipeline evidence audit: verified structured contracts; independent confusion labels:",
              result["confusion_matrix_status"])
        return 0
    except AuditError as exc:
        print(f"::error title=Pipeline evidence contract failed::{exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
