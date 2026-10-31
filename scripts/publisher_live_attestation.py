#!/usr/bin/env python3
"""Recheck every published proxy identity near publication, without curation.

The producer's release manifest stays immutable. This separate credential-free
receipt records actual fresh certificate-verified HTTPS through an isolated
sing-box outbound, and the failures/unsupported identities. Low rank, unknown
country or high latency never remove a node from the canonical feeds.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Any, Callable


_PROOF_NAME = "publisher-authentication.json"
_REASON_RE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


def _digest(uri: str) -> str:
    from huntx.formats.npvt import canonical_proxy_identity

    return hashlib.sha256(canonical_proxy_identity(uri).encode("utf-8")).hexdigest()


def _source_coordinates(root: Path) -> dict[str, Any]:
    path = root / "manifests" / "publication.json"
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("missing authoritative publisher source coordinates") from exc
    if not isinstance(source, dict):
        raise ValueError("invalid authoritative source coordinates")
    result = {
        "source_run_id": str(source.get("source_run_id", "")),
        "source_run_attempt": source.get("source_run_attempt"),
        "source_commit": source.get("source_commit"),
    }
    if (not result["source_run_id"].isdecimal()
            or type(result["source_run_attempt"]) is not int
            or result["source_run_attempt"] <= 0
            or not isinstance(result["source_commit"], str)
            or re.fullmatch(r"[0-9a-f]{40}", result["source_commit"]) is None):
        raise ValueError("invalid authoritative publisher source coordinates")
    return result


def _inventory(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    from huntx.formats.proxy_uri_validator import validate_proxy_uri

    feeds: dict[str, dict[str, Any]] = {}
    unique_links: dict[str, str] = {}
    for stem in ("all_sources", "all_sources_sub"):
        producer_path = root / "outputs" / f"{stem}.txt"
        public_path = root / "docs" / "artifacts" / "release" / f"{stem}.txt"
        try:
            producer = producer_path.read_bytes()
            public = public_path.read_bytes()
            producer_lines = [line.strip() for line in producer.decode("utf-8").splitlines()
                              if line.strip()]
            public_lines = [line.strip() for line in public.decode("utf-8").splitlines()
                            if line.strip()]
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"{stem}: missing or invalid publication feed") from exc

        def ids_for(lines: list[str]) -> dict[str, str]:
            ids: dict[str, str] = {}
            for line in lines:
                if not validate_proxy_uri(line):
                    raise ValueError(f"{stem}: malformed published proxy identity")
                digest = _digest(line)
                if digest in ids:
                    raise ValueError(f"{stem}: duplicate semantic proxy identities")
                ids[digest] = line
            return ids

        original = ids_for(producer_lines)
        rendered = ids_for(public_lines)
        if set(original) != set(rendered):
            raise ValueError(f"{stem}: producer/public feed identity mismatch")
        for digest, link in original.items():
            unique_links.setdefault(digest, link)
        feeds[stem] = {
            "producer_sha256": hashlib.sha256(producer).hexdigest(),
            "public_sha256": hashlib.sha256(public).hexdigest(),
            "identity_count": len(original),
            "_identities": sorted(original),
        }
    if not feeds["all_sources"]["identity_count"]:
        raise ValueError("empty primary feed has no authenticated publisher candidates")
    return feeds, unique_links


def _valid_measurement(fields: dict[str, Any], now: float) -> tuple[float, float, float]:
    if fields.get("probe_kind") != "protocol_authenticated":
        raise ValueError("publisher probe lacks authenticated protocol evidence")
    if fields.get("probe_authenticated") is not True:
        raise ValueError("publisher probe did not assert an authenticated HTTPS path")
    values = [fields.get(key) for key in
              ("probe_checked_at", "probe_expires_at", "latency_ms")]
    if (any(type(value) not in (int, float) or not math.isfinite(value)
            for value in values)
            or values[0] <= 0 or values[0] > now
            or not 0 < values[1] - values[0] <= 300.001
            or not 0 <= values[2] <= 30000):
        raise ValueError("publisher authenticated measurement is invalid or fabricated")
    return float(values[0]), float(values[1]), float(values[2])


def build_attestation(
    root: Path,
    *,
    source_run_id: str,
    source_run_attempt: int,
    source_commit: str,
    probe: Callable[[list[dict[str, Any]]], Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Recheck the union once, then reconcile each feed without dropping nodes."""
    source = _source_coordinates(root)
    if (str(source_run_id) != source["source_run_id"]
            or source_run_attempt != source["source_run_attempt"]
            or source_commit != source["source_commit"]):
        raise ValueError("publisher source run/attempt/commit mismatch")
    feeds, links = _inventory(root)
    if probe is None:
        from huntx.core.proxy_health import verified_records
        probe = verified_records
    checked = probe([{"data": {"line": uri}} for uri in links.values()])
    ledger = getattr(checked, "gate_report", None)
    if not isinstance(checked, list) or not isinstance(ledger, dict):
        raise ValueError("publisher probe did not provide an authenticated gate ledger")
    dispositions = ledger.get("identities")
    reasons = ledger.get("reasons")
    if (not isinstance(dispositions, dict)
            or not isinstance(reasons, dict)
            or ledger.get("schema_version") != 1
            or ledger.get("scope") != "single_authenticated_https_sweep"
            or set(dispositions) != set(links)
            or type(ledger.get("candidates")) is not int
            or ledger["candidates"] != len(links)
            or any(not isinstance(status, str)
                   or _REASON_RE.fullmatch(status) is None
                   for status in dispositions.values())
            or any(type(count) is not int or count < 0 for count in reasons.values())
            or Counter(dispositions.values()) != Counter(reasons)):
        raise ValueError("publisher HTTPS gate did not reconcile all candidates")

    captured: dict[str, dict[str, Any]] = {}
    for record in checked:
        fields = record.get("data") if isinstance(record, dict) else None
        uri = fields.get("line") if isinstance(fields, dict) else None
        if not isinstance(uri, str):
            raise ValueError("publisher authenticated probe omitted its private identity")
        key = _digest(uri)
        if key not in links or key in captured or dispositions.get(key) != "admitted":
            raise ValueError("publisher authenticated probe returned an unmatched identity")
        captured[key] = fields
    if (ledger.get("admitted") != len(captured)
            or ledger.get("rejected") != len(links) - len(captured)
            or {key for key, state in dispositions.items() if state == "admitted"}
            != set(captured)):
        raise ValueError("publisher HTTPS admission count does not match returned identities")

    clock = time.time() if now is None else float(now)
    if not math.isfinite(clock) or clock <= 0:
        raise ValueError("invalid publisher publication clock")
    identities: dict[str, dict[str, Any]] = {}
    fresh = 0
    for digest, status in sorted(dispositions.items()):
        if status != "admitted":
            identities[digest] = {"status": status}
            continue
        checked_at, expires_at, duration = _valid_measurement(captured[digest], clock)
        alive = expires_at > clock
        state: dict[str, Any] = {
            "status": "fresh_authenticated" if alive else "expired_before_publication",
            "checked_at": checked_at,
            "expires_at": expires_at,
            "duration_ms": duration,
        }
        identities[digest] = state
        fresh += int(alive)

    published_feeds: dict[str, dict[str, Any]] = {}
    for stem, data in feeds.items():
        digests = data["_identities"]
        published_feeds[stem] = {
            "producer_sha256": data["producer_sha256"],
            "public_sha256": data["public_sha256"],
            "identity_count": data["identity_count"],
            "fresh_authenticated_count": sum(
                identities[d]["status"] == "fresh_authenticated" for d in digests
            ),
            "identity_digests": digests,
        }
    report = {
        "schema_version": 1,
        "evidence_kind": "publisher_isolated_certificate_verified_https",
        "identity_algorithm": "sha256-of-canonical-proxy-identity",
        **source,
        "attested_at": datetime.fromtimestamp(clock, timezone.utc).isoformat(),
        "candidate_count": len(links),
        "fresh_authenticated_count": fresh,
        "feeds": published_feeds,
        "identities": identities,
        "limitations": [
            "Proves only individual supported sing-box HTTPS paths at recorded times",
            "Expired or failed handshakes remain candidates, never freshly verified",
            "Does not assert QUIC/REALITY/WS/gRPC beyond the tested engine outbound",
            "Does not establish exit country or anonymity from server IP or URI remark",
        ],
    }
    verify_attestation(root, report, now=clock)
    return report


def verify_attestation(root: Path, report: dict[str, Any], *,
                       now: float | None = None) -> bool:
    """Verify source identity, feed conservation and all *still-live* claims."""
    if not isinstance(report, dict):
        raise ValueError("invalid publisher authentication receipt")
    source = _source_coordinates(root)
    if any(report.get(key) != value for key, value in source.items()):
        raise ValueError("publisher attestation source commit/run mismatch")
    feeds, links = _inventory(root)
    captured = report.get("identities")
    published = report.get("feeds")
    if (report.get("schema_version") != 1
            or report.get("evidence_kind")
            != "publisher_isolated_certificate_verified_https"
            or not isinstance(captured, dict) or not isinstance(published, dict)
            or set(captured) != set(links) or set(published) != set(feeds)
            or report.get("candidate_count") != len(links)):
        raise ValueError("publisher attestation identity inventory mismatch")
    clock = time.time() if now is None else float(now)
    if not math.isfinite(clock) or clock <= 0:
        raise ValueError("invalid publisher verification clock")
    fresh: set[str] = set()
    for digest, details in captured.items():
        if not isinstance(details, dict):
            raise ValueError("publisher attestation contains malformed identity evidence")
        status = details.get("status")
        if status == "fresh_authenticated":
            checked_at, expires_at, duration = (
                details.get("checked_at"), details.get("expires_at"),
                details.get("duration_ms")
            )
            if (any(type(v) not in (int, float) or not math.isfinite(v)
                    for v in (checked_at, expires_at, duration))
                    or checked_at > clock or expires_at <= clock
                    or expires_at - checked_at > 300.001
                    or checked_at <= 0 or not 0 <= duration <= 30000):
                raise ValueError("publisher authentication expired before publication")
            fresh.add(digest)
        elif not isinstance(status, str) or _REASON_RE.fullmatch(status) is None:
            raise ValueError("invalid publisher probe disposition")
    if len(fresh) != report.get("fresh_authenticated_count") or not fresh:
        raise ValueError("no fresh authenticated publisher handshakes remain")
    for stem, metadata in feeds.items():
        saved = published[stem]
        if (not isinstance(saved, dict)
                or saved.get("identity_count") != metadata["identity_count"]
                or saved.get("producer_sha256") != metadata["producer_sha256"]
                or saved.get("public_sha256") != metadata["public_sha256"]
                or saved.get("identity_digests") != metadata["_identities"]
                or saved.get("fresh_authenticated_count")
                != len(fresh.intersection(metadata["_identities"]))):
            raise ValueError(f"{stem}: publisher feed digest/identity mismatch")
    return True

def finalize_attestation(root: Path, report: dict[str, Any], *,
                         now: float | None = None) -> dict[str, Any]:
    """Remove expired *claims*, never expired proxy identities or feed lines."""
    clock = time.time() if now is None else float(now)
    if not math.isfinite(clock) or clock <= 0:
        raise ValueError("invalid publisher finalization clock")
    # A round trip through JSON makes a private copy without sharing nested
    # state with the original proof. The report is credential-free.
    updated = json.loads(json.dumps(report))
    identities = updated.get("identities")
    if not isinstance(identities, dict):
        raise ValueError("invalid publisher attestation identity inventory")
    for details in identities.values():
        if isinstance(details, dict) and details.get("status") == "fresh_authenticated":
            expires = details.get("expires_at")
            if type(expires) not in (int, float) or not math.isfinite(expires):
                raise ValueError("invalid publisher authenticated proof expiry")
            if expires <= clock:
                details["status"] = "expired_during_publication"
    fresh = {key for key, value in identities.items()
             if isinstance(value, dict) and value.get("status") == "fresh_authenticated"}
    updated["fresh_authenticated_count"] = len(fresh)
    feeds = updated.get("feeds")
    if not isinstance(feeds, dict):
        raise ValueError("invalid publisher feed inventory")
    for metadata in feeds.values():
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("identity_digests"), list
        ):
            raise ValueError("invalid publisher identity listing")
        metadata["fresh_authenticated_count"] = sum(
            key in fresh for key in metadata["identity_digests"]
        )
    updated["finalized_at"] = datetime.fromtimestamp(clock, timezone.utc).isoformat()
    verify_attestation(root, updated, now=clock)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "finalize", "verify"))
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--source-run-id")
    parser.add_argument("--source-run-attempt", type=int)
    parser.add_argument("--source-commit")
    parser.add_argument("--producer-receipt", type=Path)
    args = parser.parse_args()
    if args.producer_receipt is not None:
        producer = json.loads(args.producer_receipt.read_text(encoding="utf-8"))
        if not isinstance(producer, dict) or producer.get("release_eligible") is not True:
            raise ValueError("publisher live proof requires explicit producer eligibility")
        if producer.get("empty_release") is True:
            print("Explicit empty release: no working-proxy attestation asserted")
            return 0

    root = args.snapshot_root.resolve()
    path = root / "manifests" / _PROOF_NAME
    if args.action == "build":
        if not args.source_run_id or not args.source_run_attempt or not args.source_commit:
            parser.error("build requires source run, attempt and commit")
        report = build_attestation(
            root, source_run_id=args.source_run_id,
            source_run_attempt=args.source_run_attempt,
            source_commit=args.source_commit,
        )
        path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
        from scripts.assemble_generated_snapshot import write_snapshot_digest
        write_snapshot_digest(root)
        print(f"Publisher HTTPS recheck: candidates={report['candidate_count']} "
              f"fresh={report['fresh_authenticated_count']} receipt={path.name}")
    else:
        report = json.loads(path.read_text(encoding="utf-8"))
        if args.action == "finalize":
            report = finalize_attestation(root, report)
            path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                            encoding="utf-8")
            from scripts.assemble_generated_snapshot import write_snapshot_digest
            write_snapshot_digest(root)
        else:
            verify_attestation(root, report)
        print(f"Publisher authentication remains fresh: {report['fresh_authenticated_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
