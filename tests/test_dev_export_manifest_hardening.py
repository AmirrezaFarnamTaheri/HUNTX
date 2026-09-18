"""Dev-export and caption-template contract regressions."""
import json

from huntx.config.schema import DestinationConfig
from pathlib import Path


def test_default_caption_template_formats_with_publish_arguments():
    template = DestinationConfig(chat_id="chat", mode="telegram").caption_template
    caption = template.format(timestamp="2026-09-18 00:00:00", sha12="abc", count=3, format="npvt")
    assert "2026-09-18" in caption


def test_publish_fallback_template_matches_schema_default():
    schema_default = DestinationConfig(chat_id="chat", mode="telegram").caption_template
    source = (Path(__file__).resolve().parents[1] / "src" / "huntx" / "pipeline" / "publish.py").read_text(encoding="utf-8")
    fallback = source.split('dest.get("caption_template", "', 1)[1].split('"', 1)[0]
    assert fallback == schema_default


def test_dev_export_drops_non_numeric_first_seen(tmp_path):
    from huntx.core.orchestrator import Orchestrator

    dev = tmp_path / "dev"
    dev.mkdir()
    (dev / "_manifest.json").write_text(
        '{"vmess://one": "not-a-number", "vmess://two": 12.5}', encoding="utf-8"
    )

    class Repo:
        def get_records_for_build(self, formats, source_ids):
            return [
                {"data": {"line": "vmess://one"}},
                {"data": {"line": "vmess://two"}},
            ]

    # An approved source backs both URIs, mirroring production; the dev-manifest
    # contract may prune to these, but the non-numeric timestamp must still be
    # dropped by the loader before the deterministic sort runs.
    source = type("S", (), {"id": "src1", "publication_eligible": True})()
    fake = type("Fake", (), {})()
    fake.paths = type("P", (), {"dev_output_dir": dev})()
    fake.repo = Repo()
    fake.config = type("C", (), {"sources": [source]})()
    Orchestrator._export_dev_outputs(fake, [])

    manifest = json.loads((dev / "_manifest.json").read_text(encoding="utf-8"))
    # The corrupt string entry must not survive; the still-approved URI is either
    # kept (with a numeric timestamp) or re-seeded numerically from state.
    assert isinstance(manifest.get("vmess://two"), (int, float))
    if "vmess://one" in manifest:
        assert isinstance(manifest["vmess://one"], (int, float))
    assert not any(isinstance(value, str) for value in manifest.values())
