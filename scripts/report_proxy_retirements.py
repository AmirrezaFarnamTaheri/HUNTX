"""Report lifecycle suppression and permanent revocation without raw links.

This report is diagnostic only. Permanent death must be an explicit, supported
policy decision; short-term reachability or transient authenticated failures
never automatically become a non-revivable terminal verdict.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

from huntx.state.proxy_retirement import (
    get_retirement_audit,
    get_suppression_candidates,
)


class _ReadOnlyDB:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        uri = "file:" + quote(str(self.path.resolve()), safe="/") + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=8)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = {
        "schema_version": 1,
        "observed_at": int(time.time()),
        "policy": "terminal_only_by_explicit_decision",
        "status": "evidence_unavailable",
        "counts": {},
        "retest_candidates": [],
    }
    if args.db.is_file():
        try:
            store = _ReadOnlyDB(args.db)
            result["counts"] = get_retirement_audit(store)
            result["retest_candidates"] = get_suppression_candidates(store)
            result["status"] = "complete"
        except (sqlite3.Error, OSError):
            # Do not turn missing/corrupt evidence into a clean bill of health.
            pass

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(
        "proxy-lifecycle: %s permanent=%s suppressed=%s evidence_insufficient=%s"
        % (
            result["status"],
            result["counts"].get("permanent_exclusions", 0),
            result["counts"].get("suppressed_candidates", 0),
            result["counts"].get("insufficient_evidence", 0),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
