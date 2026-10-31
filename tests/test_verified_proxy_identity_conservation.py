"""Every authenticated proxy must survive unchanged into its public feed.

No ranking, low speed, missing country, or duplicate display remark may quietly
remove an identity already authenticated by the producer. The final publication
tree must reconcile evidence by canonical connection identity, not by count.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from huntx.formats.npvt import canonical_proxy_identity
from scripts.validate_pages_package import validate_pages_package


SLOW = "trojan://slow-secret@5.5.5.5:443?security=tls#slow"
FAST = "trojan://fast-secret@5.5.5.6:443?security=tls#fast"
UNKNOWN_COUNTRY = "vless://543a9e39-7830-4dda-bd75-08b4319d1c7a@edge.example:443?security=tls#unknown"


def digest(uri: str) -> str:
    return hashlib.sha256(canonical_proxy_identity(uri).encode("utf-8")).hexdigest()


def stage(tmp_path, stem: str, lines: list[str], authenticated: list[str],
          admitted: list[str] | None = None) -> None:
    """Create internally well-formed but optionally inconsistent release files."""
    release = tmp_path / "artifacts" / "release"
    release.mkdir(parents=True, exist_ok=True)
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (release / f"{stem}.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    records = {
        digest(uri): {"checked_at": 1700000000, "expires_at": 1700000300,
                      "duration_ms": 30 if uri == FAST else 30000}
        for uri in authenticated
    }
    (release / f"{stem}_health.json").write_text(
        json.dumps({"schema_version": 1, "evidence": "publisher_authenticated_https",
                    "admitted_count": len(records), "records": records}),
        encoding="utf-8",
    )
    if admitted is None:
        admitted = list(lines)
    admissions = {digest(uri): "admitted" for uri in admitted}
    (release / f"{stem}_gate.json").write_text(
        json.dumps({"schema_version": 1, "scope": "single_authenticated_https_sweep",
                    "candidates": len(admissions), "admitted": len(admissions),
                    "rejected": 0, "reasons": {"admitted": len(admissions)},
                    "identities": admissions}),
        encoding="utf-8",
    )


@pytest.mark.parametrize("stem", ["all_sources", "all_sources_sub"])
def test_rejects_authenticated_identity_silently_missing_from_published_feed(tmp_path, stem):
    stage(tmp_path, stem, [FAST], [FAST, SLOW], admitted=[FAST])
    with pytest.raises(ValueError, match="(authenticated|identity|sidecar|feed)"):
        validate_pages_package(tmp_path)


@pytest.mark.parametrize("stem", ["all_sources", "all_sources_sub"])
def test_rejects_admitted_identity_silently_missing_from_published_feed(tmp_path, stem):
    stage(tmp_path, stem, [FAST], [FAST], admitted=[FAST, SLOW])
    with pytest.raises(ValueError, match="(admitted|identity|gate|feed)"):
        validate_pages_package(tmp_path)


def test_rejects_same_count_but_substituted_authenticated_identity(tmp_path):
    stage(tmp_path, "all_sources", [FAST, SLOW], [FAST, UNKNOWN_COUNTRY])
    with pytest.raises(ValueError, match="(authenticated|identity|sidecar|feed)"):
        validate_pages_package(tmp_path)


def test_preserves_all_authenticated_low_speed_and_unknown_country_nodes(tmp_path):
    stage(tmp_path, "all_sources", [FAST, SLOW, UNKNOWN_COUNTRY],
          [FAST, SLOW, UNKNOWN_COUNTRY])
    stage(tmp_path, "all_sources_sub", [SLOW, UNKNOWN_COUNTRY],
          [SLOW, UNKNOWN_COUNTRY])
    # The final validator must not impose rank, latency, country, or top-N cutoffs.
    assert validate_pages_package(tmp_path)["missing"] == []


def test_rejects_semantic_duplicate_under_different_display_remarks(tmp_path):
    same = FAST.replace("#fast", "#another-remark")
    stage(tmp_path, "all_sources", [FAST, same], [FAST], admitted=[FAST])
    with pytest.raises(ValueError, match="(duplicate|identity|feed)"):
        validate_pages_package(tmp_path)
