"""Transform enrichment must be lossless, private, deterministic and optional."""
import json
from unittest.mock import Mock, patch

from huntx.formats.npvt import NpvtHandler
from huntx.pipeline.transform import TransformPipeline


UUID = "11111111-2222-3333-4444-555555555555"


def build_pipeline(monkeypatch, tmp_path, *, dataset=None):
    if dataset is None:
        monkeypatch.delenv("HUNTX_NETWORK_INTELLIGENCE_PATH", raising=False)
    else:
        monkeypatch.setenv("HUNTX_NETWORK_INTELLIGENCE_PATH", str(dataset))
    raw_store = Mock()
    raw_store.get.return_value = (
        f"vless://{UUID}@1.1.1.1:443?security=tls#Upstream-secret-tag\n"
        f"vless://{UUID}@host.example.com:443#DE\n"
    ).encode()
    repo = Mock()
    handler = NpvtHandler()
    registry = Mock()
    registry.get.return_value = handler
    pipeline = TransformPipeline(raw_store, repo, registry, max_workers=1)
    return pipeline, handler


def test_transform_preserves_raw_proxy_uris_while_adding_endpoint_evidence(monkeypatch, tmp_path):
    dataset = tmp_path / "prefixes.json"
    dataset.write_text(json.dumps({
        "schema_version": 1, "provider": "fixture",
        "observed_at": 1800000000, "expires_at": 1800086400,
        "prefixes": [{"cidr": "1.1.1.0/24", "asn": 13335, "anycast": True}],
    }), encoding="utf-8")
    monkeypatch.setattr("huntx.core.endpoint_intelligence.time.time", lambda: 1800000100)
    pipeline, handler = build_pipeline(monkeypatch, tmp_path, dataset=dataset)
    row = {"id": 7, "source_id": "src", "raw_hash": "a" * 64, "filename": "sample.txt"}
    with patch("huntx.pipeline.transform.decide_format", return_value="npvt"):
        result = pipeline._process_single_file(row)
    assert result["status"] == "ok" and result["records"] == 2
    payloads = [json.loads(row[-1]) for row in result["record_rows"]]
    assert payloads[0]["endpoint"]["asn"] == 13335
    assert payloads[0]["endpoint"]["geo"]["country_code"] is None
    assert payloads[1]["endpoint"]["geo"]["status"] == "unresolved_hostname"
    assert payloads[1]["endpoint"]["asn"] is None
    assert payloads[0]["line"].startswith("vless://")
    assert handler.build([{"data": item} for item in payloads]) == handler.build(
        [{"data": {"line": item["line"]}} for item in payloads]
    )


def test_missing_or_invalid_dataset_does_not_stop_ingestion(monkeypatch, tmp_path):
    missing = tmp_path / "does-not-exist"
    pipeline, _ = build_pipeline(monkeypatch, tmp_path, dataset=missing)
    row = {"id": 7, "source_id": "src", "raw_hash": "b" * 64, "filename": "sample.txt"}
    with patch("huntx.pipeline.transform.decide_format", return_value="npvt"):
        result = pipeline._process_single_file(row)
    assert result["status"] == "ok"
    for encoded in (record[-1] for record in result["record_rows"]):
        item = json.loads(encoded)
        assert item["endpoint"]["asn"] is None
        assert item["endpoint"]["intelligence"]["status"] == "unavailable"
