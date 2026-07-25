from __future__ import annotations

import json
import time
from typing import Any, Iterable, Optional


def upsert_record_verdict(
    db: Any,
    *,
    unique_hash: str,
    record_type: str,
    syntax_status: str,
    parser_version: str,
    probe_status: str,
    policy_status: str,
    policy_version: str,
    policy_tier: str,
    probe_checked_at: Optional[float] = None,
    probe_expires_at: Optional[float] = None,
    reason_codes: Iterable[str] = (),
    updated_at: Optional[float] = None,
) -> None:
    now = float(updated_at if updated_at is not None else time.time())
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO record_verdicts (
                unique_hash, record_type, syntax_status, parser_version,
                probe_status, probe_checked_at, probe_expires_at,
                policy_status, policy_version, policy_tier,
                reason_codes_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(unique_hash, record_type, policy_tier) DO UPDATE SET
                syntax_status=excluded.syntax_status,
                parser_version=excluded.parser_version,
                probe_status=excluded.probe_status,
                probe_checked_at=excluded.probe_checked_at,
                probe_expires_at=excluded.probe_expires_at,
                policy_status=excluded.policy_status,
                policy_version=excluded.policy_version,
                reason_codes_json=excluded.reason_codes_json,
                updated_at=excluded.updated_at
            """,
            (
                unique_hash,
                record_type,
                syntax_status,
                parser_version,
                probe_status,
                probe_checked_at,
                probe_expires_at,
                policy_status,
                policy_version,
                policy_tier,
                json.dumps(sorted(set(reason_codes))),
                now,
            ),
        )


def get_records_for_governed_build(
    db: Any,
    record_types: list[str],
    allowed_source_ids: list[str],
    *,
    min_seen_file_id: Optional[int] = None,
    publication_tier: str = "compatible",
    require_fresh_probe: bool = False,
    now_epoch: Optional[float] = None,
) -> list[dict[str, Any]]:
    if not record_types or not allowed_source_ids:
        return []
    type_marks = ",".join("?" for _ in record_types)
    source_marks = ",".join("?" for _ in allowed_source_ids)
    args: list[Any] = list(record_types) + list(allowed_source_ids)
    extra = ""
    if min_seen_file_id is not None:
        extra += " AND s.id > ?"
        args.append(int(min_seen_file_id))
    verdict_join = ""
    verdict_where = ""
    if publication_tier == "secure":
        verdict_join = """
            JOIN record_verdicts v
              ON v.unique_hash = r.unique_hash
             AND v.record_type = r.record_type
             AND v.policy_tier = 'secure'
        """
        verdict_where = " AND v.syntax_status = 'pass' AND v.policy_status = 'pass'"
        if require_fresh_probe:
            verdict_where += (
                " AND v.probe_status = 'pass'" " AND v.probe_expires_at IS NOT NULL" " AND v.probe_expires_at > ?"
            )
            args.append(float(now_epoch if now_epoch is not None else time.time()))
    query = f"""
        WITH filtered AS (
            SELECT r.id, r.record_type, r.unique_hash, r.data_json
            FROM records r
            JOIN seen_files s ON r.source_file_hash = s.raw_hash
            {verdict_join}
            WHERE r.record_type IN ({type_marks})
              AND s.source_id IN ({source_marks})
              AND r.is_active = 1
              {extra}
              {verdict_where}
        ), dedup AS (
            SELECT record_type, unique_hash, MAX(id) AS keep_id
            FROM filtered
            GROUP BY record_type, unique_hash
        )
        SELECT f.record_type, f.unique_hash, f.data_json
        FROM filtered f
        JOIN dedup d ON d.keep_id = f.id
        ORDER BY f.id ASC
    """
    with db.connect() as conn:
        rows = conn.execute(query, args).fetchall()
    return [
        {
            "record_type": row["record_type"],
            "unique_hash": row["unique_hash"],
            "data": json.loads(row["data_json"]),
        }
        for row in rows
    ]
