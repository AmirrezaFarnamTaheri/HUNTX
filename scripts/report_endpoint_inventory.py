#!/usr/bin/env python3
"""Produce sanitized endpoint metadata inventory, including historical records.

Reads persisted active, processed NPVT observations without mutating the DB.
Legacy URI records are enriched in memory, so deploying a new metadata
contract does not require a risky rewrite of existing canonical observations.
No raw URI, hostname, credential, password, query or remark leaves this report.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from huntx.core.endpoint_intelligence import PrefixIntelligence, describe_proxy_endpoint

_MAX_SCAN = 50_000
_MAX_JSON_BYTES = 32_768
_MAX_OUTPUT_ENDPOINTS = 1500


def load_active_observations(
    db_path: Path,
    *,
    limit: int,
) -> tuple[list[tuple[str, str]], bool] | None:
    """Read a bounded population of current, provenanced, processed records."""
    if not db_path.is_file() or type(limit) is not int or not 1 <= limit <= _MAX_SCAN:
        return None
    try:
        connection = sqlite3.connect(
            "file:" + db_path.resolve().as_posix() + "?mode=ro",
            uri=True, timeout=8,
        )
        try:
            rows = connection.execute(
                "SELECT s.source_id, r.data_json "
                "FROM records r "
                "JOIN seen_files s ON s.id = r.source_observation_id "
                "WHERE r.is_active = 1 AND r.record_type = 'npvt' "
                "AND s.status = 'processed' "
                "ORDER BY r.id DESC LIMIT ?",
                (limit + 1,),
            ).fetchall()
        finally:
            connection.close()
    except (sqlite3.Error, OSError):
        return None
    return [(str(source_id), str(data)) for source_id, data in rows[:limit]], len(rows) > limit


def build_inventory(
    observations: Iterable[tuple[str, str]],
    *,
    observed_at: int,
    limit: int,
    truncated: bool = False,
    intelligence: PrefixIntelligence | None = None,
) -> dict[str, Any]:
    """Aggregate safe endpoint evidence; never copy untrusted record fields."""
    counts = {
        "records_scanned": 0,
        "invalid_records": 0,
        "distinct_endpoint_ids": 0,
        "unresolved_geo": 0,
        "unattributed_asn": 0,
        "anycast_endpoints": 0,
        "attributed_cdn_endpoints": 0,
    }
    distinct: dict[str, dict[str, Any]] = {}
    sources: dict[str, set[str]] = {}
    for source_id, blob in observations:
        if counts["records_scanned"] >= limit:
            truncated = True
            break
        counts["records_scanned"] += 1
        if not isinstance(blob, str) or len(blob.encode("utf-8")) > _MAX_JSON_BYTES:
            counts["invalid_records"] += 1
            continue
        try:
            item = json.loads(blob)
        except (ValueError, TypeError):
            counts["invalid_records"] += 1
            continue
        line = item.get("line") if isinstance(item, dict) else None
        if not isinstance(line, str) or not line:
            counts["invalid_records"] += 1
            continue
        description = describe_proxy_endpoint(line, intelligence=intelligence)
        if description is None:
            counts["invalid_records"] += 1
            continue
        key = description["endpoint_id"]
        if key not in distinct:
            # Deliberate allowlist: hostnames and IP literals are omitted from
            # published diagnostics; only a stable endpoint fingerprint remains.
            safe = {
                "endpoint_id": key,
                "protocol": description["protocol"],
                "port": description["port"],
                "ip_version": description["ip_version"],
                "host_kind": description["host_kind"],
                "transport_kind": description["transport_kind"],
                "transport": description["transport"],
                "tls_mode": description["tls_mode"],
                "asn": description["asn"],
                "as_org": description["as_org"],
                "cdn_provider": description["cdn_provider"],
                "anycast": description["anycast"],
                "geo": dict(description["geo"]),
                "attribution_status": description["intelligence"]["status"],
                "observation_count": 0,
            }
            distinct[key] = safe
            sources[key] = set()
        distinct[key]["observation_count"] += 1
        sources[key].add(source_id)

    for key, data in distinct.items():
        data["source_count"] = len(sources[key])
        counts["unresolved_geo"] += data["geo"]["country_code"] is None
        counts["unattributed_asn"] += data["asn"] is None
        counts["anycast_endpoints"] += data["anycast"] is True
        counts["attributed_cdn_endpoints"] += data["cdn_provider"] is not None
    counts["distinct_endpoint_ids"] = len(distinct)
    output = sorted(distinct.values(), key=lambda e: (-e["observation_count"], e["endpoint_id"]))
    return {
        "schema_version": 1,
        "scope": "public_endpoint_metadata_not_proxy_authentication",
        "observed_at": int(observed_at),
        "status": "truncated" if truncated else "complete",
        "counts": counts,
        "endpoints_truncated": len(output) > _MAX_OUTPUT_ENDPOINTS,
        "endpoints": output[:_MAX_OUTPUT_ENDPOINTS],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-records", type=int, default=10_000)
    args = parser.parse_args()
    if not 1 <= args.max_records <= _MAX_SCAN:
        parser.error(f"--max-records must be between 1 and {_MAX_SCAN}")
    evidence: PrefixIntelligence | None = None
    dataset = os.environ.get("HUNTX_NETWORK_INTELLIGENCE_PATH", "").strip()
    if dataset:
        try:
            evidence = PrefixIntelligence.from_file(dataset)
        except (OSError, ValueError):
            print("::warning title=Network intelligence unavailable::Using unknown ASN/CDN/geo where evidence is absent")
    records = load_active_observations(args.db, limit=args.max_records)
    if records is None:
        snapshot: dict[str, Any] = {
            "schema_version": 1,
            "scope": "public_endpoint_metadata_not_proxy_authentication",
            "observed_at": int(time.time()),
            "status": "evidence_unavailable",
            "counts": {"records_scanned": 0},
            "endpoints_truncated": False,
            "endpoints": [],
        }
    else:
        rows, truncated = records
        snapshot = build_inventory(
            rows, observed_at=int(time.time()), limit=args.max_records,
            truncated=truncated, intelligence=evidence,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(snapshot, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    counts = snapshot["counts"]
    print(
        "endpoint-inventory: status=%s records=%s unique=%s geo_unknown=%s asn_unknown=%s"
        % (
            snapshot["status"], counts.get("records_scanned", 0),
            counts.get("distinct_endpoint_ids", 0),
            counts.get("unresolved_geo", 0), counts.get("unattributed_asn", 0),
        )
    )
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with Path(step_summary).open("a", encoding="utf-8") as f:
            f.write(
                "\n### Network endpoint metadata\n\n"
                f"- Snapshot: `{snapshot['status']}`\n"
                f"- Parsed records: `{counts.get('records_scanned', 0)}`\n"
                f"- Distinct endpoints: `{counts.get('distinct_endpoint_ids', 0)}`\n"
                f"- Unknown geo / ASN: `{counts.get('unresolved_geo', 0)}` / `{counts.get('unattributed_asn', 0)}`\n"
                "- No link credentials, physical-location inference from remarks, "
                "or authenticated proxy-health claims\n"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
