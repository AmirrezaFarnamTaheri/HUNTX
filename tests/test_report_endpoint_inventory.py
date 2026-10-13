"""Red/green contracts for sanitized historical endpoint metadata reports."""

import json
import sqlite3

from scripts.report_endpoint_inventory import build_inventory, load_active_observations


URI = "vless://11111111-2222-3333-4444-555555555555@1.1.1.1:443#old-france"


def _db(tmp_path):
    path = tmp_path / "state.db"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE seen_files (
                id INTEGER PRIMARY KEY, source_id TEXT, status TEXT
            );
            CREATE TABLE records (
                id INTEGER PRIMARY KEY, source_observation_id INTEGER,
                unique_hash TEXT, record_type TEXT, data_json TEXT,
                is_active INTEGER
            );
        """)
        db.executemany(
            "INSERT INTO seen_files VALUES (?, ?, ?)",
            [(1, "approved", "processed"), (2, "failed-source", "failed")],
        )
        db.executemany(
            "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, 1, "one", "npvt", json.dumps({"line": URI}), 1),
                (2, 1, "two", "npvt", json.dumps({
                    "line": URI.replace("11111111-2222-3333-4444-555555555555", "22222222-2222-4222-8222-222222222222")
                }), 1),
                (3, 1, "three", "npvt", json.dumps({
                    "line": "trojan://secret@edge.example.com:443#Germany"
                }), 1),
                (4, 2, "four", "npvt", json.dumps({"line": URI}), 1),
                (5, 1, "old", "npvt", json.dumps({"line": URI}), 0),
                (6, 1, "opaque", "other", json.dumps({"line": URI}), 1),
            ],
        )
    return path


def test_report_enriches_previous_records_without_mutating_sqlite(tmp_path):
    db = _db(tmp_path)
    rows, truncated = load_active_observations(db, limit=100)
    assert not truncated
    assert len(rows) == 3
    before = db.read_bytes()
    snapshot = build_inventory(rows, observed_at=1800000000, limit=100)
    assert db.read_bytes() == before
    assert snapshot["counts"]["records_scanned"] == 3
    assert snapshot["counts"]["distinct_endpoint_ids"] == 2
    assert snapshot["counts"]["unresolved_geo"] == 2
    assert snapshot["counts"]["unattributed_asn"] == 2
    assert snapshot["status"] == "complete"
    assert snapshot["scope"] == "public_endpoint_metadata_not_proxy_authentication"
    ip = next(node for node in snapshot["endpoints"] if node["protocol"] == "vless")
    assert ip["source_count"] == 1
    assert ip["observation_count"] == 2
    assert ip["ip_version"] == 4
    content = json.dumps(snapshot, sort_keys=True)
    assert "vless://" not in content
    assert "trojan://" not in content
    assert "secret" not in content
    assert "11111111" not in content
    assert "1.1.1.1" not in content
    assert "edge.example.com" not in content


def test_report_rejects_invalid_syntax_and_bounded_rows_without_leaking_payload():
    observations = [
        ("src", '{"line":"not-a-proxy","password":"secret"}'),
        ("src", '{"line":true}'),
        ("src", "bad-json-secret"),
        ("src", '{"line":"vless://secret@x.example.com:443"}'),
    ]
    result = build_inventory(observations, observed_at=1800000000, limit=20)
    assert result["counts"]["invalid_records"] == 3
    assert result["counts"]["distinct_endpoint_ids"] == 1
    assert "secret" not in json.dumps(result)


def test_report_marks_missing_database_as_unavailable(tmp_path):
    result = load_active_observations(tmp_path / "missing.db", limit=10)
    assert result is None


def test_scan_limit_provides_explicit_truncation(tmp_path):
    db = _db(tmp_path)
    rows, truncated = load_active_observations(db, limit=2)
    assert truncated
    assert len(rows) == 2
    report = build_inventory(rows, observed_at=1800000000, limit=2, truncated=truncated)
    assert report["status"] == "truncated"
    assert report["counts"]["records_scanned"] == 2


def test_inventory_exposes_protocol_transport_tls_ip_family_and_evidence_coverage(tmp_path):
    db = _db(tmp_path)
    rows, truncated = load_active_observations(db, limit=100)
    snapshot = build_inventory(rows, observed_at=1800000000, limit=100, truncated=truncated)
    dimensions = snapshot["distributions"]
    assert dimensions["protocol"] == {"trojan": 1, "vless": 1}
    assert dimensions["host_kind"] == {"dns_name": 1, "public_ip_literal": 1}
    assert dimensions["tls_mode"]["none"] >= 1
    assert dimensions["transport_kind"]["tcp"] == 2
    assert snapshot["counts"]["duplicate_endpoint_observations"] == 1
    assert snapshot["counts"]["dns_endpoints"] == 1
    assert snapshot["counts"]["network_endpoints"] == 2


def test_inventory_rejects_unreasonably_big_payload_without_logging_secrets():
    huge = '{"line":"vless://secret@x.example.com:443","extra":"' + 'X' * 50000 + '"}'
    report = build_inventory([("src", huge)], observed_at=1800000000, limit=1)
    assert report["counts"]["invalid_records"] == 1
    assert "secret" not in json.dumps(report)
