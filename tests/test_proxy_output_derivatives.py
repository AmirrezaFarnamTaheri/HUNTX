from __future__ import annotations

import base64
import json
from unittest.mock import Mock

import pytest

from huntx.bot.constants import _ALL_VALID_FORMATS
from huntx.bot.delivery import DeliveryMixin
from huntx.config.validate import _validate_route_format
from huntx.core.output_ownership import _frozen_alias_payloads, output_filename
from huntx.pipeline.build import BuildPipeline

_VALID_REALITY_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


class _Registry:
    def list_formats(self):
        return ["npvt", "npvtsub"]

    def can_build(self, fmt: str) -> bool:
        return fmt in {"npvt", "npvtsub"}


def _build_results(proxy_text: bytes):
    state_repo = Mock()
    artifact_store = Mock()
    registry = Mock()
    pipeline = BuildPipeline(state_repo, artifact_store, registry)
    state_repo.get_records_for_build.return_value = [
        {"record_type": "npvt", "data": {"line": "placeholder"}}
    ]
    handler = Mock()
    handler.build.return_value = proxy_text
    registry.get.return_value = handler
    artifact_store.save_artifact.return_value = "base-hash"

    results = pipeline.run(
        {"name": "all_sources", "formats": ["npvt"], "from_sources": ["src1"]}
    )
    return results, artifact_store


def test_proxy_build_emits_raw_xray_and_nekobox_derivatives():
    proxy_text = (
        b"vless://11111111-2222-3333-4444-555555555555@example.com:443"
        + f"?security=reality&pbk={_VALID_REALITY_KEY}".encode()
        + b"&sid=ab12&sni=cdn.example.com"
        b"&type=grpc&serviceName=grpcsvc&fp=chrome#My%20Node\n"
        b"trojan://second-secret@second.example.com:443?sni=second.example.com#Second%20Node\n"
    )

    results, artifact_store = _build_results(proxy_text)
    by_format = {result["format"]: result for result in results}

    # The raw URI list is the base product itself; there is no separate raw
    # derivative to carry the same bytes a second time.
    assert by_format["npvt"]["data"] == proxy_text
    assert "npvt.raw.txt" not in by_format

    # The universal subscription is a lossless 1:1 encoding of the raw node
    # list: N source lines must decode back to N independent subscription lines.
    decoded_subscription = base64.b64decode(by_format["npvt.b64sub"]["data"]).decode("utf-8")
    assert decoded_subscription == proxy_text.decode("utf-8").strip()
    assert len(decoded_subscription.splitlines()) == 2

    xray = json.loads(by_format["npvt.xray.json"]["data"].decode("utf-8"))
    proxy = xray["outbounds"][0]
    assert proxy["tag"] == "My Node"
    assert proxy["protocol"] == "vless"
    assert proxy["settings"] == {
        "address": "example.com",
        "port": 443,
        "id": "11111111-2222-3333-4444-555555555555",
        "encryption": "none",
    }
    assert proxy["streamSettings"]["method"] == "grpc"
    assert proxy["streamSettings"]["grpcSettings"] == {"serviceName": "grpcsvc"}
    assert proxy["streamSettings"]["security"] == "reality"
    assert proxy["streamSettings"]["realitySettings"] == {
        "serverName": "cdn.example.com",
        "fingerprint": "chrome",
        "password": _VALID_REALITY_KEY,
        "shortId": "ab12",
    }

    nekobox = json.loads(by_format["npvt.nekobox.json"]["data"].decode("utf-8"))
    assert set(nekobox) == {"outbounds"}
    assert [outbound["type"] for outbound in nekobox["outbounds"]] == ["vless", "trojan"]
    assert [outbound["tag"] for outbound in nekobox["outbounds"]] == ["My Node", "Second Node"]
    assert len(nekobox["outbounds"]) == 2
    assert all(key not in nekobox for key in ("dns", "route", "routing", "inbounds"))

    # The node subscription must preserve the full config's REAL proxy
    # cardinality. Selector/urltest/direct helpers are not proxies and do not
    # become subscription entries.
    singbox = json.loads(by_format["npvt.singbox.json"]["data"].decode("utf-8"))
    helper_types = {"selector", "urltest", "direct", "block", "dns"}
    singbox_proxy_outbounds = [
        outbound
        for outbound in singbox["outbounds"]
        if outbound.get("type") not in helper_types
    ]
    assert len(nekobox["outbounds"]) == len(singbox_proxy_outbounds)

    clash_lines = by_format["npvt.clash.yaml"]["data"].decode("utf-8").splitlines()
    assert clash_lines[0] == "proxies:"
    clash_items = [
        json.loads(line[4:]) for line in clash_lines[1:] if line.startswith("  - ")
    ]
    assert [item["name"] for item in clash_items] == ["My Node", "Second Node"]
    assert len(clash_items) == 2

    saved_formats = {call.args[1] for call in artifact_store.save_output.call_args_list}
    assert {"npvt.xray.json", "npvt.nekobox.json", "npvt.clash.yaml"} <= saved_formats
    # The raw pass-through is not a product: it is byte-for-byte the base
    # artifact, and the URLs earlier runs published stay alive as frozen
    # aliases of the base output instead.
    assert "npvt.raw.txt" not in saved_formats


def test_xray_derivative_is_omitted_when_no_node_is_faithfully_representable():
    results, _ = _build_results(
        b"anytls://secret@any.example.com:443?sni=any.example.com#AnyTLS\n"
    )

    formats = {result["format"] for result in results}
    assert "npvt" in formats
    assert "npvt.singbox.json" in formats
    assert "npvt.nekobox.json" in formats
    assert "npvt.xray.json" not in formats


def test_new_derivatives_have_canonical_output_filenames():
    """Published names drop the internal format segment."""
    assert output_filename("all_sources", "npvt") == "all_sources.txt"
    assert output_filename("all_sources", "npvt.b64sub") == "all_sources_base64.txt"
    assert output_filename("all_sources", "npvt.decoded.json") == "all_sources.json"
    assert output_filename("all_sources", "npvt.singbox.json") == "all_sources_singbox.json"
    assert output_filename("all_sources", "npvt.xray.json") == "all_sources_xray.json"
    assert output_filename("all_sources", "npvt.nekobox.json") == "all_sources_nekobox.json"
    assert output_filename("all_sources", "npvt.clash.yaml") == "all_sources_clash.yaml"
    # Formats outside the proxy family keep the route.format convention.
    assert output_filename("all_sources", "ovpn") == "all_sources.ovpn"


def test_every_published_url_ever_handed_out_still_resolves():
    """A rename that 404s an existing subscriber link is an outage, not a rename."""
    payloads = {
        output_filename("all_sources", fmt): (b"payload", {"route": "all_sources", "format": fmt})
        for fmt in ("npvt", "npvt.b64sub", "npvt.decoded.json", "npvt.singbox.json",
                    "npvt.xray.json", "npvt.nekobox.json")
    }
    frozen = _frozen_alias_payloads(payloads)
    for name in (
        "all_sources.npvt",
        "all_sources.npvt.raw.txt",
        "all_sources_npvt_raw.txt",
        "all_sources.npvt.b64sub",
        "all_sources_npvt_b64sub.txt",
        "all_sources_npvt_decoded.json",
        "all_sources_npvt_singbox.json",
        "all_sources_npvt_xray.json",
        "all_sources_npvt_nekobox.json",
    ):
        assert name in frozen, name
        # The alias must be a byte-identical copy, not a fresh build.
        canonical = payloads[output_filename("all_sources", "npvt")][0] if name.endswith(
            ("npvt", "raw.txt")) else None
        assert frozen[name][0] == b"payload"
        assert canonical is None or frozen[name][0] == canonical
    # A canonical name is never published a second time under itself.
    assert not (set(frozen) & set(payloads))


@pytest.mark.parametrize(
    "fmt",
    [
        "raw.txt",
        "xray.json",
        "nekobox.json",
        "clash.yaml",
        "npvt.raw.txt",
        "npvt.xray.json",
        "npvt.nekobox.json",
        "npvt.clash.yaml",
        "npvtsub.raw.txt",
        "npvtsub.xray.json",
        "npvtsub.nekobox.json",
        "npvtsub.clash.yaml",
    ],
)
def test_route_config_rejects_new_automatic_derivative_outputs(fmt):
    with pytest.raises(ValueError, match="derived output"):
        _validate_route_format(_Registry(), "route", fmt)  # type: ignore[arg-type]


def test_bot_exposes_and_matches_new_derived_formats():
    assert {"raw.txt", "xray.json", "nekobox.json", "clash.yaml"} <= set(_ALL_VALID_FORMATS)
    # The canonical names and the frozen ones both resolve.
    assert DeliveryMixin._filename_matches_format("all_sources.txt", "npvt")
    assert DeliveryMixin._filename_matches_format("all_sources.txt", "raw.txt")
    assert DeliveryMixin._filename_matches_format("all_sources.npvt", "npvt")
    assert DeliveryMixin._filename_matches_format("all_sources_npvt_raw.txt", "raw.txt")
    assert DeliveryMixin._filename_matches_format("all_sources_singbox.json", "singbox.json")
    assert DeliveryMixin._filename_matches_format("all_sources_xray.json", "xray.json")
    assert DeliveryMixin._filename_matches_format("all_sources_nekobox.json", "nekobox.json")
    assert DeliveryMixin._filename_matches_format("all_sources_clash.yaml", "clash.yaml")
    assert DeliveryMixin._filename_matches_format("all_sources_base64.txt", "b64sub")
    assert DeliveryMixin._filename_matches_format("all_sources.json", "decoded.json")
    # ...and the names that never belonged to this route are not matched.
    assert not DeliveryMixin._filename_matches_format("all_sources.txt", "xray.json")
