"""Stage old read-only release fixtures without weakening the production gate.

Only the scheduled/CI development refresh uses this adapter. The immutable
producer snapshot, its release receipt and its published artifacts are not
modified; strict production duplicate-identity checks remain mandatory.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from huntx.formats.npvt import canonical_proxy_identity


def stage_legacy_release_fixture(source: Path, destination: Path) -> dict[str, int]:
    """Copy an old snapshot and normalize semantic duplicates in the copy.

    Old committed snapshots can contain different share-link spellings for
    the same connection. New production runs must reject such duplicates,
    but a read-only periodic dev generator should still exercise the current
    exporter against the last available historical fixtures. Never print or
    return credentials, raw URIs, or the connection identities themselves.
    """
    source = Path(source)
    destination = Path(destination)
    source_feed = source / "all_sources.txt"
    if not source_feed.is_file():
        raise ValueError("missing historical release feed")
    lines = [
        line.strip()
        for line in source_feed.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not lines:
        raise ValueError("empty historical release feed")
    seen: set[str] = set()
    retained: list[str] = []
    for line in lines:
        identity = canonical_proxy_identity(line)
        if identity in seen:
            continue
        seen.add(identity)
        retained.append(line)
    shutil.copytree(source, destination)
    (destination / "all_sources.txt").write_text(
        "\n".join(retained) + "\n", encoding="utf-8"
    )
    return {
        "input": len(lines),
        "retained": len(retained),
        "duplicate_identities": len(lines) - len(retained),
    }
