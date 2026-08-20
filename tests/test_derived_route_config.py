from __future__ import annotations

import pytest

from huntx.config.validate import _validate_route_format


class _Registry:
    def list_formats(self):
        return ["npvt", "npvtsub", "slipnet"]

    def can_build(self, fmt: str) -> bool:
        return fmt in {"npvt", "npvtsub"}


@pytest.mark.parametrize(
    "fmt",
    [
        "b64sub",
        "decoded.json",
        "singbox.json",
        "npvt.b64sub",
        "npvt.decoded.json",
        "npvt.singbox.json",
        "npvtsub.b64sub",
    ],
)
def test_route_config_rejects_automatic_derivative_outputs(fmt):
    with pytest.raises(ValueError, match="derived output"):
        _validate_route_format(_Registry(), "route", fmt)  # type: ignore[arg-type]


def test_route_config_accepts_base_proxy_format_that_generates_derivatives():
    _validate_route_format(_Registry(), "route", "npvt")  # type: ignore[arg-type]


def test_route_config_still_rejects_parse_only_format():
    with pytest.raises(ValueError, match="parse-only"):
        _validate_route_format(_Registry(), "route", "slipnet")  # type: ignore[arg-type]
