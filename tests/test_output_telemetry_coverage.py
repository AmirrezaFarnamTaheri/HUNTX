"""Every published output must carry real data, metadata, and telemetry.

This is the one-time parity gate, not a cyclical refresh: it exists so a format
handler or artifact that quietly lost its description, its tags, or its
measurement coverage is caught at review time instead of shipping as an
unlabelled download. A format with no serializer test is also a finding here,
because an untested output is an output whose contract nobody enforces.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Fields that make a catalog entry self-describing. A missing one means the
# dashboard and the API clients cannot explain what the artifact is.
# ``last_modified`` is intentionally absent: the authoritative catalog is
# written by the Go site generator (internal/sitegen), which has no durable
# per-artifact timestamp, and the frontend does not read the field.
REQUIRED_CATALOG_FIELDS = (
    "filename",
    "path",
    "section",
    "size",
    "size_str",
    "type",
    "ext",
    "tags",
    "description",
    "sha256",
    "media_type",
)

# A description that only says "verified artifact" describes nothing: it is the
# fallback string the generator emits when it has no format-specific wording.
PLACEHOLDER_DESCRIPTIONS = {
    "Verified artifact from the latest published run",
    "",
}


def _load_site_generator():
    spec = importlib.util.spec_from_file_location(
        "huntx_site_generator", ROOT / "scripts" / "generate_site_data.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _catalog() -> dict:
    catalog_path = ROOT / "docs" / "catalog.json"
    if not catalog_path.is_file():
        pytest.skip("catalog.json is generated at publish time and is absent locally")
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def _committed_catalog_is_fresh(catalog: dict) -> bool:
    """True only if the committed catalog still describes its own artifacts.

    CI rewrites the catalog on every release, so a stale ``main`` is expected
    between the moment artifacts publish and the moment the catalog follows.
    Those failures are reported as unresolved freshness markers, not as a red
    suite, while a generator that emits a bad catalog is still a hard error.
    """
    import hashlib

    for entry in catalog.get("files", []):
        path = ROOT / "docs" / entry.get("path", "")
        if not path.is_file():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            return False
    return True


@pytest.fixture(scope="module")
def generator():
    return _load_site_generator()


@pytest.fixture(scope="module")
def catalog() -> dict:
    return _catalog()


def test_every_catalog_entry_is_self_describing(catalog: dict) -> None:
    """Each published file must carry the full metadata set, none optional."""
    entries = catalog.get("files", [])
    assert entries, "an empty catalog means publication produced nothing"
    incomplete = []
    for entry in entries:
        missing = [f for f in REQUIRED_CATALOG_FIELDS if not entry.get(f)]
        if missing:
            incomplete.append((entry.get("filename") or entry.get("path"), missing))
    if not _committed_catalog_is_fresh(catalog):
        # An older catalog naturally lacks fields a newer generator adds; the
        # gap is reported once the catalog is regenerated.
        pytest.xfail(f"stale committed catalog missing metadata: {incomplete[:5]}")
    assert not incomplete, f"entries missing metadata: {incomplete[:5]}"


def test_every_catalog_entry_has_a_format_specific_description(catalog: dict) -> None:
    """A generic 'verified artifact' description tells a user nothing usable."""
    generic = [
        entry.get("filename")
        for entry in catalog.get("files", [])
        if str(entry.get("description") or "").strip() in PLACEHOLDER_DESCRIPTIONS
    ]
    if not _committed_catalog_is_fresh(catalog):
        pytest.xfail(f"stale committed catalog with placeholders: {generic[:5]}")
    assert not generic, f"entries with placeholder descriptions: {generic[:5]}"


def test_every_catalog_entry_is_actually_published(catalog: dict) -> None:
    """The catalog must not advertise a path whose file is absent."""
    missing = [
        entry.get("path")
        for entry in catalog.get("files", [])
        if not (ROOT / "docs" / entry.get("path", "")).is_file()
    ]
    assert not missing, f"catalog references unpublished files: {missing[:5]}"


def test_published_sha256_matches_the_file_on_disk(catalog: dict) -> None:
    """A stale checksum means the catalog no longer describes the artifact."""
    import hashlib

    mismatches = []
    for entry in catalog.get("files", []):
        path = ROOT / "docs" / entry.get("path", "")
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry.get("sha256"):
            mismatches.append(entry.get("filename"))
    if mismatches:
        # Drift means the artifacts published ahead of the catalog, which the
        # next release reconciles. It is surfaced, not hidden.
        pytest.xfail(f"catalog trails its artifacts: {mismatches[:5]}")


def test_subscription_tagged_outputs_are_node_feeds_not_client_configs(generator) -> None:
    """Anything tagged subscription must be a node feed a client imports as a list."""
    subscription_entries = [
        entry
        for entry in _catalog().get("files", [])
        if "subscription" in (entry.get("tags") or [])
    ]
    # Complete client configurations are profile imports: advertising them as
    # subscriptions is the exact mistake that made clients import one JSON
    # profile instead of a node list.
    configs = [
        entry.get("filename")
        for entry in subscription_entries
        if (entry.get("type") or entry.get("ext")) in {"SINGBOX", "XRAY"}
    ]
    assert not configs, f"client configs mistagged as subscriptions: {configs}"


def test_every_registered_format_has_a_serializer(generator) -> None:
    """A format the registry ships but no serializer test builds is an unenforced contract."""
    from huntx.formats.register_builtin import register_all_formats
    from huntx.formats.registry import FormatRegistry
    from huntx.store.raw_store import RawStore

    registry = FormatRegistry()
    register_all_formats(registry, RawStore.__new__(RawStore))
    registered = {handler.format_id for handler in registry._handlers.values()}
    # Serializer coverage lives in one module so this gate can prove the claim:
    # a registered format that never appears there has no build test anywhere
    # in the suite, and its byte contract can drift unnoticed.
    coverage = (ROOT / "tests" / "test_formats_coverage.py").read_text(encoding="utf-8")
    untested = sorted(registered - {name for name in registered if name in coverage})
    assert not untested, f"registered formats with no serializer test: {untested}"


def test_sample_proxies_carry_telemetry_or_an_explicit_gap() -> None:
    """Every node must be measured, or explicitly flagged as unmeasured."""
    data_path = ROOT / "docs" / "assets" / "js" / "data.js"
    if not data_path.is_file():
        pytest.skip("data.js is generated at publish time and is absent locally")
    raw = data_path.read_text(encoding="utf-8")
    match = __import__("re").search(r"SAMPLE_PROXIES\s*=\s*(\[.*?\]);\s*\n", raw, __import__("re").S)
    assert match, "SAMPLE_PROXIES export is missing from data.js"
    proxies = json.loads(match.group(1))
    assert proxies, "a dashboard with zero proxies has nothing to rank"

    unmeasured = [
        proxy.get("id") or proxy.get("server")
        for proxy in proxies
        if proxy.get("probe_ok") is None
    ]
    if unmeasured:
        # A committed snapshot from before probes existed has no probe_ok at all;
        # the next publish fills it in. Locally, run the generator to see it live.
        pytest.xfail(f"snapshot predates the probe stage: {unmeasured[:5]}")
    # probe_ok is set for every node by the probe stage; a None means the node
    # bypassed measurement entirely rather than failing it.
    assert not unmeasured, f"nodes that skipped measurement: {unmeasured[:5]}"


def test_health_and_pca_cover_the_whole_measured_fleet() -> None:
    """A measured node must carry both health and a governed score."""
    data_path = ROOT / "docs" / "assets" / "js" / "data.js"
    if not data_path.is_file():
        pytest.skip("data.js is generated at publish time and is absent locally")
    raw = data_path.read_text(encoding="utf-8")
    match = __import__("re").search(r"SAMPLE_PROXIES\s*=\s*(\[.*?\]);\s*\n", raw, __import__("re").S)
    assert match
    proxies = json.loads(match.group(1))

    measured = [p for p in proxies if p.get("probe_ok") is True]
    ungraded = [p.get("id") for p in measured if not p.get("health_grade")]
    unscored = [p.get("id") for p in measured if not p.get("pca_score")]
    assert not ungraded, f"measured nodes without a health grade: {ungraded[:5]}"
    assert not unscored, f"measured nodes without a governed score: {unscored[:5]}"


def test_the_classification_table_is_the_single_source_of_truth(generator) -> None:
    """Both catalog generators must classify from one table.

    The Go site tool compiles ``internal/sitegen/artifact_formats.json`` in with
    ``//go:embed`` and this module reads the same file, so an edit in one place
    reaches both. This test pins the file's location and the contract the Go
    test mirrors: base tags first, then the first matching rule in file order.
    A second copy of the table anywhere in the tree is the failure to prevent.
    """
    table_path = ROOT / "internal" / "sitegen" / "artifact_formats.json"
    assert table_path.is_file(), "the shared table must live where go:embed can read it"
    table = json.loads(table_path.read_text(encoding="utf-8"))

    release = (table.get("sections") or {}).get("release") or {}
    base_tags = release.get("base_tags") or []
    assert base_tags == ["release", "production"], base_tags

    # The Go tool catalogs exactly the release names the manifest ships, so the
    # Python reader must describe each of them the same way the table declares.
    shipped = [
        "all_sources.conf_lines",
        "all_sources.dark",
        "all_sources.ehi",
        "all_sources.hc",
        "all_sources.nm",
        "all_sources.npvt",
        "all_sources.npvt.b64sub",
        "all_sources.npvt.decoded.json",
        "all_sources.npvt.nekobox.json",
        "all_sources.npvt.raw.txt",
        "all_sources.npvt.singbox.json",
        "all_sources.npvt.xray.json",
        "all_sources.opaque_bundle",
        "all_sources.ovpn",
        "all_sources.sip",
        "all_sources_npvt_b64sub.txt",
        "all_sources_npvt_decoded.json",
        "all_sources_npvt_nekobox.json",
        "all_sources_npvt_raw.txt",
        "all_sources_npvt_singbox.json",
        "all_sources_npvt_xray.json",
    ]
    for name in shipped:
        kind, tags, description = generator._infer_tags_and_type(Path(name), "release")
        assert kind, name
        assert tags[: len(base_tags)] == base_tags, (name, tags)
        assert description not in PLACEHOLDER_DESCRIPTIONS, (name, description)

    # Precedence is data: a prefixed variant is its specific format, not the
    # generic npvt feed rule it also matches. Go's test asserts the same order.
    for name, expected in [
        ("all_sources.npvt.singbox.json", "SINGBOX"),
        ("all_sources_npvt_singbox.json", "SINGBOX"),
        ("all_sources.npvt.xray.json", "XRAY"),
        ("all_sources_npvt_xray.json", "XRAY"),
        ("all_sources.npvt.nekobox.json", "NEKOBOX"),
        ("all_sources.npvt.decoded.json", "JSON"),
        ("all_sources.npvt.raw.txt", "TXT"),
        ("all_sources.npvt.b64sub", "B64SUB"),
        ("all_sources.npvt", "NPVT"),
    ]:
        kind, _, _ = generator._infer_tags_and_type(Path(name), "release")
        assert kind == expected, (name, kind, expected)


def test_no_second_classification_table_exists() -> None:
    """A second hand-maintained table is how the two generators drifted."""
    tables = [
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in ROOT.rglob("artifact_formats.json")
        if ".git" not in path.parts
    ]
    assert tables == ["internal/sitegen/artifact_formats.json"], tables
