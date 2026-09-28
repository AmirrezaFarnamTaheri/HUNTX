"""The dashboard product mapping has exactly one source, and both writers read it.

The publisher is a workflow_run consumer: it checks out the current code but
consumes a dist produced by whichever pipeline run last succeeded, which may
predate the artifact rename. Both catalog writers must therefore accept the
canonical names *and* every frozen alias, and they must resolve them from the
same table, or publication fails ("catalog file count mismatch" in Go) or the
dashboard silently ships an empty baked catalog (in Python).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "internal" / "sitegen" / "artifact_formats.json"

CANONICAL = {
    "all_sources.txt",
    "all_sources_base64.txt",
    "all_sources.json",
    "all_sources_singbox.json",
    "all_sources_xray.json",
    "all_sources_nekobox.json",
}
PRE_RENAME = {
    "all_sources.npvt",
    "all_sources.npvt.raw.txt",
    "all_sources_npvt_raw.txt",
    "all_sources.npvt.b64sub",
    "all_sources_npvt_b64sub.txt",
    "all_sources_npvt_decoded.json",
    "all_sources_npvt_singbox.json",
    "all_sources_npvt_xray.json",
    "all_sources_npvt_nekobox.json",
}


def _table() -> dict:
    return json.loads(TABLE.read_text(encoding="utf-8"))


def _load_site_data():
    spec = importlib.util.spec_from_file_location(
        "generate_site_data_probe", ROOT / "scripts" / "generate_site_data.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_product_mapping_lives_in_the_shared_table() -> None:
    products = _table().get("products")
    assert isinstance(products, dict) and products, "artifact_formats.json must declare products"
    # A product is keyed by its canonical name and lists that name first.
    for product, filenames in products.items():
        assert filenames, f"{product} lists no filename"
        assert filenames[0] == product, f"{product} must list its canonical name first"


def test_every_canonical_and_frozen_name_is_representable() -> None:
    listed = {name for names in _table()["products"].values() for name in names}
    assert CANONICAL <= listed, f"missing canonical: {sorted(CANONICAL - listed)}"
    assert PRE_RENAME <= listed, f"missing frozen alias: {sorted(PRE_RENAME - listed)}"


def test_no_filename_is_claimed_by_two_products() -> None:
    owner: dict[str, str] = {}
    for product, filenames in _table()["products"].items():
        for name in filenames:
            assert name not in owner, f"{name} claimed by {owner.get(name)} and {product}"
            owner[name] = product


def test_python_writer_admits_both_naming_eras() -> None:
    module = _load_site_data()
    for name in CANONICAL:
        assert module._is_frontend_product("release", name), name
    for name in PRE_RENAME:
        assert module._is_frontend_product("release", name), name
    # A specialist format is still not a dashboard product.
    for name in ("all_sources.ovpn", "all_sources.opaque_bundle", "all_sources.conf_lines"):
        assert not module._is_frontend_product("release", name), name


def test_python_writer_resolves_an_alias_to_its_canonical_product() -> None:
    module = _load_site_data()
    for alias in PRE_RENAME:
        product = module._product_for_artifact(alias)
        assert product in CANONICAL, f"{alias} resolved to {product!r}"
    assert module._product_for_artifact("all_sources.ovpn") is None


def test_the_go_writer_reads_the_same_table_rather_than_its_own_copy() -> None:
    """A second mapping in Go would drift with nothing to notice.

    The Go side's behaviour is covered by internal/sitegen/rename_compat_test.go,
    which drives Generate over pre-rename, post-rename and mixed dists.
    """
    source = (ROOT / "internal" / "sitegen" / "sitegen.go").read_text(encoding="utf-8")
    assert "frontendReleaseProducts" not in source, (
        "the product mapping must come from artifact_formats.json, not a Go copy"
    )
    assert '"products"' in source, "the Go struct must decode the products section"
