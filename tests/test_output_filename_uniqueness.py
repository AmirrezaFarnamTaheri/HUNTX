"""Every published name must be unique per (route, format), for every format
the real production config enables.

The rename dropped the internal format segment from published names, which is
only sound while no two enabled formats of one route want the same name. The
test suite historically used a single-format fixture, so a route enabling both
``npvt`` and ``npvtsub`` - which configs/config.prod.yaml does - was never
exercised, and every derived product of the two families resolved to the same
filename. That collision cannot be caught by ``configured_output_identities``,
because derived products are not configured formats; it only fires at export
time, as a RuntimeError, after a full run.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from huntx.core.output_ownership import (  # noqa: E402
    _DERIVED_CANONICAL_SUFFIX,
    output_filename,
)
from huntx.pipeline.build import _DERIVED_PROXY_FORMATS  # noqa: E402


def _production_formats() -> list[str]:
    """Read the formats the shipped production config enables."""
    import yaml

    config = yaml.safe_load((ROOT / "configs" / "config.prod.yaml").read_text(encoding="utf-8"))
    formats: list[str] = []
    for route in (config.get("publishing") or {}).get("routes") or []:
        for fmt in route.get("formats") or []:
            if fmt not in formats:
                formats.append(str(fmt))
    return formats


def _all_identities(route: str, formats: list[str]) -> list[tuple[str, str]]:
    """Every filename the build could emit for one route, as (filename, format)."""
    identities: list[tuple[str, str]] = []
    for fmt in formats:
        identities.append((output_filename(route, fmt), fmt))
        if fmt in _DERIVED_PROXY_FORMATS:
            for dotted in _DERIVED_CANONICAL_SUFFIX:
                derived = f"{fmt}{dotted}"
                identities.append((output_filename(route, derived), derived))
    return identities


def test_production_config_enables_more_than_one_derived_proxy_format() -> None:
    """Guards the premise: a single-format fixture would not catch a collision."""
    formats = _production_formats()
    derived_formats = [f for f in formats if f in _DERIVED_PROXY_FORMATS]
    assert len(derived_formats) >= 2, (
        "the production config is expected to enable npvt and npvtsub; if this "
        "changed, re-check the derived filename stems"
    )
    assert "npvt" in derived_formats and "npvtsub" in derived_formats


@pytest.mark.parametrize("route", ["all_sources", "prod", "Route With Spaces"])
def test_every_enabled_format_gets_a_distinct_filename(route: str) -> None:
    identities = _all_identities(route, _production_formats())
    seen: dict[str, str] = {}
    for filename, fmt in identities:
        assert filename not in seen, (
            f"{fmt!r} and {seen[filename]!r} both publish as {filename!r}"
        )
        seen[filename] = fmt


def test_the_primary_feed_keeps_the_undotted_conventional_names() -> None:
    """npvt is the primary feed, so its products carry no stem at all."""
    assert output_filename("all_sources", "npvt") == "all_sources.txt"
    assert output_filename("all_sources", "npvt.b64sub") == "all_sources_base64.txt"
    assert output_filename("all_sources", "npvt.decoded.json") == "all_sources.json"
    assert output_filename("all_sources", "npvt.singbox.json") == "all_sources_singbox.json"
    assert output_filename("all_sources", "npvt.xray.json") == "all_sources_xray.json"
    assert output_filename("all_sources", "npvt.nekobox.json") == "all_sources_nekobox.json"


def test_the_secondary_feed_gets_the_sub_stem() -> None:
    assert output_filename("all_sources", "npvtsub") == "all_sources_sub.txt"
    assert output_filename("all_sources", "npvtsub.b64sub") == "all_sources_sub_base64.txt"
    assert output_filename("all_sources", "npvtsub.decoded.json") == "all_sources_sub.json"
    assert output_filename("all_sources", "npvtsub.singbox.json") == "all_sources_sub_singbox.json"
    assert output_filename("all_sources", "npvtsub.xray.json") == "all_sources_sub_xray.json"
    assert output_filename("all_sources", "npvtsub.nekobox.json") == "all_sources_sub_nekobox.json"


def test_an_empty_stem_is_a_value_not_a_missing_key() -> None:
    """The npvt stem is deliberately "", so a truthiness fallback would re-add it."""
    for dotted in _DERIVED_CANONICAL_SUFFIX:
        name = output_filename("all_sources", f"npvt{dotted}")
        assert "_npvt" not in name, f"the primary feed regressed to {name!r}"


def test_an_unregistered_base_format_still_gets_a_unique_stem() -> None:
    assert output_filename("all_sources", "otherfmt.singbox.json") == "all_sources_otherfmt_singbox.json"
    other = output_filename("all_sources", "npvtsub.singbox.json")
    assert output_filename("all_sources", "otherfmt.singbox.json") != other


def test_configured_output_identities_still_has_no_collision() -> None:
    from huntx.core.output_ownership import configured_output_identities

    config = SimpleNamespace(routes=[SimpleNamespace(name="all_sources", formats=_production_formats())])
    identities = configured_output_identities(config)
    assert "all_sources.txt" in identities
    assert "all_sources_sub.txt" in identities
    assert len(identities) == len(set(identities))
