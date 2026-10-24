"""Dashboard source totals describe configured, enabled and observed stages."""
import json

from scripts import generate_site_data as site


def test_source_counts_use_same_run_evidence_and_do_not_inflate_enabled(tmp_path, monkeypatch):
    config = tmp_path / "production.yaml"
    config.write_text(
        "sources:\n"
        "- id: alpha\n  type: telegram_user\n"
        "- id: beta\n  type: http_subscription\n  enabled: false\n"
        "- id: gamma\n  type: http_subscription\n",
        encoding="utf-8",
    )
    health = tmp_path / "source-health.json"
    health.write_text(json.dumps({
        "schema_version": 1, "run_id": "42",
        "counts": {
            "configured_sources": 3, "enabled": 2, "disabled": 1,
            "telegram_observed": 1, "http_retrieved": 1,
            "http_source_failures": 0, "telegram_not_observed": 0
        }
    }), encoding="utf-8")
    monkeypatch.setattr(site, "CONFIG_PROD_FILE", config)
    monkeypatch.setattr(site, "OUTPUTS_DEV_DIR", tmp_path / "no-history")
    monkeypatch.setenv("HUNTX_SOURCE_RUN_ID", "42")
    monkeypatch.setenv("HUNTX_SOURCE_HEALTH_REPORT", str(health))
    stats = site.compute_aggregate_stats([], {
        "total_files": 4, "total_size": 100, "total_size_str": "100 B"
    })
    assert stats["configured_sources_count"] == 3
    assert stats["enabled_sources_count"] == 2
    assert stats["observed_sources_count"] == 2
    assert stats["active_sources_count"] == 2
    assert stats["catalog_product_count"] == 4

    monkeypatch.setenv("HUNTX_SOURCE_RUN_ID", "43")
    stale = site.compute_aggregate_stats([], {
        "total_files": 4, "total_size": 100, "total_size_str": "100 B"
    })
    assert stale["observed_sources_count"] is None
