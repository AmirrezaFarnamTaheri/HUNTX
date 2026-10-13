"""Conservative evidence gate for unreliable proxy identities.

A 'dead for ever' label is not supportable from TCP failures, transient DNS,
one vantage, or brief protocol outages. Only an explicit revocation/retirement
policy is terminal. Repeated verified protocol failures from different
vantages over several days trigger *temporary publication suppression*;
a later independently authenticated success restores eligibility.

No historical source is deleted and no secret proxy URIs are logged.
"""

from __future__ import annotations

from typing import Any

# Intentionally evaluate only immutable authenticated proxy probe history.
# Reuse the exact predicate for ordinary feeds, governed feeds and reporting.
_SUSPECT_CONDITION = """
    p.lifecycle_status = 'suspect'
    AND p.consecutive_failures >= 6
    AND p.last_probe_result = 'fail'
    AND p.last_probe_at BETWEEN
        CAST(strftime('%s', 'now') AS INTEGER) - 604800
        AND CAST(strftime('%s', 'now') AS INTEGER) + 300
    AND EXISTS (
        SELECT 1
        FROM proxy_probe_history AS h
        WHERE h.unique_hash = p.unique_hash
          AND h.record_type = p.record_type
          AND h.success = 0
          AND h.checked_at > COALESCE(p.last_success_at, 0)
        GROUP BY h.unique_hash, h.record_type
        HAVING COUNT(*) >= 6
           AND COUNT(DISTINCT h.vantage_id) >= 2
           AND MAX(h.checked_at) - MIN(h.checked_at) >= 86400
    )
"""

# p is an alias provided by the enclosing NOT EXISTS in both publication queries.
PROXY_UNPUBLISHABLE_SQL = (
    "p.lifecycle_status IN ('dead', 'revoked', 'archived') "
    f"OR ({_SUSPECT_CONDITION})"
)


def get_retirement_audit(db: Any) -> dict[str, int]:
    """Return bounded, credential-free counts; never auto-terminalize."""
    with db.connect() as connection:
        row = connection.execute(
            f"""
            SELECT
              COUNT(*) AS tracked_identities,
              COUNT(*) FILTER (
                WHERE p.lifecycle_status IN ('dead', 'revoked', 'archived')
              ) AS permanent_exclusions,
              COUNT(*) FILTER (
                WHERE ({_SUSPECT_CONDITION})
              ) AS suppressed_candidates,
              COUNT(*) FILTER (
                WHERE p.lifecycle_status = 'suspect'
                  AND NOT ({_SUSPECT_CONDITION})
              ) AS insufficient_evidence
            FROM proxy_lifecycle AS p
            """
        ).fetchone()
    return {
        key: int(row[key] or 0)
        for key in (
            "tracked_identities", "permanent_exclusions",
            "suppressed_candidates", "insufficient_evidence",
        )
    }


def get_suppression_candidates(db: Any, *, limit: int = 100) -> list[dict[str, Any]]:
    """Identify temporarily suppressed identities without revealing credentials.

    These are *retesting* candidates, not proof of permanent death. Fingerprints
    are shortened to avoid publishing source payloads or link credentials.
    """
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("candidate limit must be an integer from 1 to 1000")
    with db.connect() as connection:
        rows = connection.execute(
            f"""
            SELECT p.unique_hash, p.record_type,
                   p.consecutive_failures, p.last_probe_at
            FROM proxy_lifecycle AS p
            WHERE ({_SUSPECT_CONDITION})
            ORDER BY p.last_probe_at DESC, p.unique_hash
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "identity_fingerprint": str(row["unique_hash"])[:20],
            "record_type": row["record_type"],
            "authenticated_failure_streak": int(row["consecutive_failures"]),
            "last_authenticated_failure_at": int(row["last_probe_at"]),
            "status": "temporarily_suppressed",
            "next_action": "authenticated_retest_from_independent_vantages",
        }
        for row in rows
    ]
