import json
from types import SimpleNamespace

from huntx.core.dev_manifest_contract import prune_dev_manifest_to_eligible_sources


class _Repo:
    def get_records_for_build(self, formats, source_ids):
        assert formats == ["npvt", "npvtsub"]
        records = []
        if "approved" in source_ids:
            records.append({"data": {"line": "vless://approved@example.com:443#A"}})
        if "candidate" in source_ids:
            records.append({"data": {"line": "trojan://candidate@example.com:443#C"}})
        return records


def test_manifest_prunes_uri_from_unapproved_source(tmp_path):
    manifest_path = tmp_path / "_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "vless://approved@example.com:443": 1,
                "trojan://candidate@example.com:443": 2,
            }
        ),
        encoding="utf-8",
    )
    orchestrator = SimpleNamespace(
        config=SimpleNamespace(
            sources=[
                SimpleNamespace(id="approved", publication_eligible=True),
                SimpleNamespace(id="candidate", publication_eligible=False),
            ]
        ),
        repo=_Repo(),
    )

    pruned = prune_dev_manifest_to_eligible_sources(orchestrator, manifest_path)

    assert pruned == {"vless://approved@example.com:443": 1}
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted == pruned


def test_manifest_empties_when_no_source_is_approved(tmp_path):
    manifest_path = tmp_path / "_manifest.json"
    manifest_path.write_text(
        json.dumps({"trojan://candidate@example.com:443": 2}),
        encoding="utf-8",
    )
    orchestrator = SimpleNamespace(
        config=SimpleNamespace(
            sources=[SimpleNamespace(id="candidate", publication_eligible=False)]
        ),
        repo=_Repo(),
    )

    assert prune_dev_manifest_to_eligible_sources(orchestrator, manifest_path) == {}
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == {}
