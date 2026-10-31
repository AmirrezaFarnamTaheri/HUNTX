"""The generated-outputs branch checksum must cover its ACTUAL committed tree.

The full Pages snapshot includes seven large cumulative-history files which
are deliberately omitted from generated-outputs, so their checksum receipts
cannot be interchangeable.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import assemble_generated_snapshot as assembler


REMOVED_FROM_GIT = (
    "outputs_dev/_manifest.json",
    "outputs_dev/proxies.json",
    "outputs_dev/proxies.txt",
    "outputs_dev/proxies_b64sub.txt",
    "docs/artifacts/dev/proxies.json",
    "docs/artifacts/dev/proxies.txt",
    "docs/artifacts/dev/proxies_b64sub.txt",
)


def seed_full_snapshot(tmp_path: Path) -> Path:
    root = tmp_path / "pages-complete"
    content = {
        "manifests/publication.json": '{"source_run_id":"41252283641"}\n',
        "outputs/all_sources.txt": "trojan://secret@203.0.113.8:443\n",
        "outputs_dev/_manifest.json.gz.index.json": '{"parts":["part1"]}\n',
        "outputs_dev/_manifest.json.gz.part1": "compressed-current-history\n",
        "docs/artifacts/release/all_sources.txt": "trojan://secret@203.0.113.8:443\n",
        "docs/catalog.json": '{"files":[]}\n',
        **{path: f"large cumulative history {path}\n" for path in REMOVED_FROM_GIT},
    }
    for rel, text in content.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assembler.write_snapshot_digest(root)
    return root


def independent_tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def test_publisher_git_snapshot_digest_matches_only_the_files_it_commits(tmp_path):
    pages = seed_full_snapshot(tmp_path)
    git_snapshot = tmp_path / "git-generated-outputs"
    pages_checksum = (pages / "manifests/SHA256SUMS").read_text()
    assert pages_checksum.strip() == independent_tree_hash(pages)

    assembler.prepare_repository_snapshot(pages, git_snapshot)

    assert (pages / "manifests/SHA256SUMS").read_text() == pages_checksum
    assert assembler.verify_snapshot_digest(pages) is True
    assert assembler.verify_snapshot_digest(git_snapshot) is True
    git_checksum = (git_snapshot / "manifests/SHA256SUMS").read_text().strip()
    assert git_checksum == independent_tree_hash(git_snapshot)
    assert git_checksum != pages_checksum

    for rel in REMOVED_FROM_GIT:
        assert (pages / rel).is_file()
        assert not (git_snapshot / rel).exists()
    for rel in (
        "outputs/all_sources.txt",
        "docs/artifacts/release/all_sources.txt",
        "manifests/publication.json",
        "outputs_dev/_manifest.json.gz.index.json",
        "outputs_dev/_manifest.json.gz.part1",
    ):
        assert (git_snapshot / rel).read_bytes() == (pages / rel).read_bytes()


def test_generated_branch_commit_is_rejected_if_a_byte_changes_after_sealing(tmp_path):
    pages = seed_full_snapshot(tmp_path)
    git_snapshot = tmp_path / "git-generated-outputs"
    assembler.prepare_repository_snapshot(pages, git_snapshot)
    (git_snapshot / "outputs/all_sources.txt").write_bytes(b"modified feed\n")

    with pytest.raises(ValueError, match="(digest|checksum|SHA256SUMS|integrity)"):
        assembler.verify_snapshot_digest(git_snapshot)


def test_git_snapshot_preparation_is_fail_closed_if_source_checksum_is_stale(tmp_path):
    pages = seed_full_snapshot(tmp_path)
    (pages / "manifests/publication.json").write_text('{"source_run_id":"wrong"}\n')
    git_snapshot = tmp_path / "git-generated-outputs"

    with pytest.raises(ValueError, match="(digest|checksum|SHA256SUMS|integrity)"):
        assembler.prepare_repository_snapshot(pages, git_snapshot)
    assert not git_snapshot.exists()
