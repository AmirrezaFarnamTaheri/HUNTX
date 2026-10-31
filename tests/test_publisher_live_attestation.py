"""Publisher proof must be real authenticated HTTPS, fresh and lossless.

These tests use a deterministic probe double; the actual production path must
use the isolated sing-box engine and never infer auth from TCP or source rank.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from huntx.core.proxy_health import CheckedRecords
from huntx.formats.npvt import canonical_proxy_identity
from scripts.publisher_live_attestation import (
    build_attestation, finalize_attestation, verify_attestation,
)


FAST = "trojan://synthetic-fast@5.5.5.5:443?security=tls#Fast"
SLOW = "trojan://synthetic-slow@5.5.5.6:443?security=tls#Slow"
FAILED = "trojan://synthetic-failed@5.5.5.7:443?security=tls#Failed"
CLOCK = 1_800_000_000.0


def digest(uri):
    return hashlib.sha256(canonical_proxy_identity(uri).encode("utf-8")).hexdigest()


def snapshot(tmp_path, *, primary=None, alternate=None):
    primary = [FAST, SLOW, FAILED] if primary is None else primary
    alternate = [SLOW, FAST] if alternate is None else alternate
    a = tmp_path / "outputs"
    b = tmp_path / "docs" / "artifacts" / "release"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    for stem, links in (("all_sources", primary), ("all_sources_sub", alternate)):
        payload = ("\n".join(links) + "\n").encode()
        (a / f"{stem}.txt").write_bytes(payload)
        (b / f"{stem}.txt").write_bytes(payload)
    (tmp_path / "manifests").mkdir()
    (tmp_path / "manifests" / "publication.json").write_text(json.dumps({
        "source_run_id": "41247302977", "source_run_attempt": 1,
        "source_commit": "a" * 40,
    }))
    return tmp_path


def fake_probe(records):
    lines = [record["data"]["line"] for record in records]
    digests = [digest(line) for line in lines]
    assert len(set(digests)) == len(lines), "the publisher should probe each connection only once"
    dispositions = {digest(line): ("https_path_failed" if line == FAILED else "admitted")
                    for line in lines}
    admitted = [
        {"data": {"line": line, "probe_kind": "protocol_authenticated",
                  "probe_authenticated": True, "probe_checked_at": CLOCK - 20,
                  "probe_expires_at": CLOCK + 280,
                  "latency_ms": 7900 if line == SLOW else 20}}
        for line in lines if line != FAILED
    ]
    return CheckedRecords(admitted, {
        "schema_version": 1, "scope": "single_authenticated_https_sweep",
        "candidates": len(lines), "admitted": len(admitted),
        "rejected": len(lines) - len(admitted),
        "identities": dispositions,
        "reasons": {"admitted": len(admitted), "https_path_failed": len(lines)-len(admitted)},
    })


def build(root, probe=fake_probe, *, now=CLOCK):
    return build_attestation(root, source_run_id="41247302977",
                             source_run_attempt=1, source_commit="a" * 40,
                             probe=probe, now=now)


def test_rechecks_all_distinct_canonical_connections_and_keeps_slow_working_one(tmp_path):
    root = snapshot(tmp_path)
    result = build(root)
    assert result["source_run_id"] == "41247302977"
    assert result["source_run_attempt"] == 1
    assert result["source_commit"] == "a" * 40
    assert result["candidate_count"] == 3
    assert result["fresh_authenticated_count"] == 2
    assert result["feeds"]["all_sources"]["fresh_authenticated_count"] == 2
    assert result["feeds"]["all_sources_sub"]["fresh_authenticated_count"] == 2
    assert result["identities"][digest(SLOW)]["duration_ms"] == 7900
    assert result["identities"][digest(FAILED)]["status"] == "https_path_failed"
    assert result["identities"][digest(SLOW)]["status"] == "fresh_authenticated"
    text = json.dumps(result)
    assert "synthetic-slow@" not in text
    assert "trojan://" not in text
    assert verify_attestation(root, result, now=CLOCK) is True


def test_rejects_mismatch_between_producer_feed_and_public_download(tmp_path):
    root = snapshot(tmp_path)
    (root / "docs" / "artifacts" / "release" / "all_sources.txt").write_text(FAST + "\n")
    with pytest.raises(ValueError, match="(public|feed|identity|mismatch)"):
        build(root)


def test_rejects_no_live_authenticated_handshake_and_does_not_fake_one(tmp_path):
    root = snapshot(tmp_path)

    def all_failed(records):
        return CheckedRecords([], {
            "schema_version": 1, "scope": "single_authenticated_https_sweep",
            "candidates": len(records), "admitted": 0, "rejected": len(records),
            "identities": {digest(r["data"]["line"]): "https_path_failed" for r in records},
            "reasons": {"https_path_failed": len(records)},
        })
    with pytest.raises(ValueError, match="(fresh|authenticated|handshake)"):
        build(root, all_failed)


def test_old_handshakes_do_not_authorize_release_and_expire_before_commit(tmp_path):
    root = snapshot(tmp_path)
    report = build(root)
    with pytest.raises(ValueError, match="(expired|fresh|authentication)"):
        verify_attestation(root, report, now=CLOCK + 301)


def test_report_cannot_rewrite_source_identity_or_hide_missing_node(tmp_path):
    root = snapshot(tmp_path)
    report = build(root)
    report["source_commit"] = "b" * 40
    with pytest.raises(ValueError, match="(source|commit|mismatch)"):
        verify_attestation(root, report, now=CLOCK)
    report = build(root)
    (root / "outputs" / "all_sources_sub.txt").write_text(FAST + "\n")
    with pytest.raises(ValueError, match="(digest|feed|mismatch|identity)"):
        verify_attestation(root, report, now=CLOCK)


def test_finalization_expires_only_proof_not_working_proxy_membership(tmp_path):
    root = snapshot(tmp_path)
    report = build(root)
    # The fast observation ages out while the slower but genuine HTTPS
    # success remains alive. Do not delete the fast node from either feed.
    report["identities"][digest(FAST)]["expires_at"] = CLOCK + 230
    finalized = finalize_attestation(root, report, now=CLOCK + 240)
    assert finalized["fresh_authenticated_count"] == 1
    assert finalized["identities"][digest(FAST)]["status"] == "expired_during_publication"
    assert finalized["identities"][digest(SLOW)]["status"] == "fresh_authenticated"
    assert finalized["feeds"]["all_sources"]["identity_count"] == 3
    assert finalized["feeds"]["all_sources_sub"]["identity_count"] == 2
    assert (root / "outputs" / "all_sources.txt").read_text().count("trojan://") == 3


def test_finalization_blocks_release_when_all_publisher_proof_expires(tmp_path):
    root = snapshot(tmp_path)
    report = build(root)
    with pytest.raises(ValueError, match="(fresh|expired|authentication)"):
        finalize_attestation(root, report, now=CLOCK + 301)
