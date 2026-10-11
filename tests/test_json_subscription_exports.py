import json

from huntx.formats.common.clash import build_clash_subscription_bytes
from huntx.formats.common.nekobox import build_nekobox_outbounds_bytes
from huntx.formats.common.singbox import (
    build_singbox_config_bytes,
    build_singbox_profile_bytes,
)
from huntx.formats.common.xray import (
    build_xray_config_bytes,
    build_xray_profile_bytes,
)


TROJAN = (
    "trojan://secret@t.example.com:443"
    "?security=tls&sni=t.example.com#Node"
)


def test_singbox_subscription_is_outbounds_only() -> None:
    payload = json.loads(build_singbox_config_bytes(TROJAN).decode("utf-8"))

    assert set(payload) == {"outbounds"}
    assert len(payload["outbounds"]) == 1
    assert payload["outbounds"][0]["type"] == "trojan"
    assert "domain_resolver" not in payload["outbounds"][0]
    assert "inbounds" not in payload
    assert "dns" not in payload
    assert "route" not in payload


def test_singbox_full_profile_is_preserved_separately() -> None:
    payload = json.loads(build_singbox_profile_bytes(TROJAN).decode("utf-8"))

    assert "inbounds" in payload
    assert "dns" in payload
    assert "route" in payload
    proxy = next(item for item in payload["outbounds"] if item.get("type") == "trojan")
    assert proxy["domain_resolver"] == "google"


def test_xray_full_profile_is_preserved_separately() -> None:
    payload = json.loads(build_xray_profile_bytes(TROJAN).decode("utf-8"))

    assert "inbounds" in payload
    assert len(payload["inbounds"]) == 1
    assert payload["inbounds"][0]["protocol"] == "socks"
    assert any(item.get("protocol") == "trojan" for item in payload["outbounds"])


def test_xray_subscription_is_outbounds_only() -> None:
    payload = json.loads(build_xray_config_bytes(TROJAN).decode("utf-8"))

    assert set(payload) == {"outbounds"}
    assert len(payload["outbounds"]) == 1
    assert payload["outbounds"][0]["protocol"] == "trojan"
    assert "inbounds" not in payload
    assert "routing" not in payload


def test_nekobox_subscription_wraps_nodes_in_outbounds_object() -> None:
    payload = json.loads(build_nekobox_outbounds_bytes(TROJAN).decode("utf-8"))

    assert set(payload) == {"outbounds"}
    assert len(payload["outbounds"]) == 1
    assert payload["outbounds"][0]["type"] == "trojan"


def _clash_items(payload: bytes) -> list[dict[str, object]]:
    lines = payload.decode("utf-8").splitlines()
    assert lines and lines[0] == "proxies:"
    return [json.loads(line[4:]) for line in lines[1:] if line.startswith("  - ")]


def test_clash_subscription_is_proxies_only() -> None:
    items = _clash_items(build_clash_subscription_bytes(TROJAN))

    assert len(items) == 1
    assert items[0]["type"] == "trojan"
    assert items[0]["name"] == "Node"


def test_two_nodes_remain_two_subscription_entries() -> None:
    text = "\n".join(
        [
            TROJAN,
            "trojan://secret2@u.example.com:443"
            "?security=tls&sni=u.example.com#Node-2",
        ]
    )

    singbox = json.loads(build_singbox_config_bytes(text).decode("utf-8"))
    xray = json.loads(build_xray_config_bytes(text).decode("utf-8"))
    nekobox = json.loads(build_nekobox_outbounds_bytes(text).decode("utf-8"))
    clash = _clash_items(build_clash_subscription_bytes(text))

    assert len(singbox["outbounds"]) == 2
    assert len(xray["outbounds"]) == 2
    assert len(nekobox["outbounds"]) == 2
    assert len(clash) == 2


def test_1601_nodes_remain_1601_independent_subscription_entries() -> None:
    count = 1601
    text = "\n".join(
        f"trojan://secret-{index}@node-{index}.example.com:443"
        f"?security=tls&sni=node-{index}.example.com#Node-{index}"
        for index in range(count)
    )

    singbox = json.loads(build_singbox_config_bytes(text).decode("utf-8"))
    xray = json.loads(build_xray_config_bytes(text).decode("utf-8"))
    nekobox = json.loads(build_nekobox_outbounds_bytes(text).decode("utf-8"))
    clash = _clash_items(build_clash_subscription_bytes(text))

    assert len(singbox["outbounds"]) == count
    assert len(xray["outbounds"]) == count
    assert len(nekobox["outbounds"]) == count
    assert len(clash) == count
