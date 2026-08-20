from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from huntx.bot.constants import _ALL_VALID_FORMATS
from huntx.bot.delivery import DeliveryMixin
from huntx.config.validate import _validate_route_format
from huntx.core.output_ownership import output_filename
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
    )

    results, artifact_store = _build_results(proxy_text)
    by_format = {result["format"]: result for result in results}

    assert by_format["npvt.raw.txt"]["data"] == proxy_text

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
    assert isinstance(nekobox, dict)
    assert [outbound["type"] for outbound in nekobox["outbounds"]] == ["vless"]
    assert nekobox["outbounds"][0]["tag"] == "My Node"

    saved_formats = {call.args[1] for call in artifact_store.save_output.call_args_list}
    assert {"npvt.raw.txt", "npvt.xray.json", "npvt.nekobox.json"} <= saved_formats


def test_xray_derivative_is_omitted_when_no_node_is_faithfully_representable():
    results, _ = _build_results(
        b"anytls://secret@any.example.com:443?sni=any.example.com#AnyTLS\n"
    )

    formats = {result["format"] for result in results}
    assert "npvt.raw.txt" in formats
    assert "npvt.singbox.json" in formats
    assert "npvt.nekobox.json" in formats
    assert "npvt.xray.json" not in formats


def test_new_derivatives_have_canonical_output_filenames():
    assert output_filename("all_sources", "npvt.raw.txt") == "all_sources_npvt_raw.txt"
    assert output_filename("all_sources", "npvt.xray.json") == "all_sources_npvt_xray.json"
    assert output_filename("all_sources", "npvt.nekobox.json") == "all_sources_npvt_nekobox.json"


@pytest.mark.parametrize(
    "fmt",
    [
        "raw.txt",
        "xray.json",
        "nekobox.json",
        "npvt.raw.txt",
        "npvt.xray.json",
        "npvt.nekobox.json",
        "npvtsub.raw.txt",
        "npvtsub.xray.json",
        "npvtsub.nekobox.json",
    ],
)
def test_route_config_rejects_new_automatic_derivative_outputs(fmt):
    with pytest.raises(ValueError, match="derived output"):
        _validate_route_format(_Registry(), "route", fmt)  # type: ignore[arg-type]


def test_bot_exposes_and_matches_new_derived_formats():
    assert {"raw.txt", "xray.json", "nekobox.json"} <= set(_ALL_VALID_FORMATS)
    assert DeliveryMixin._filename_matches_format("all_sources_npvt_raw.txt", "raw.txt")
    assert DeliveryMixin._filename_matches_format("all_sources_npvt_xray.json", "xray.json")
    assert DeliveryMixin._filename_matches_format("all_sources_npvt_nekobox.json", "nekobox.json")
