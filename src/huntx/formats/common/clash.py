"""Render raw proxy URIs as a Mihomo/Clash proxy-provider subscription.

The public Clash artifact is deliberately a provider body, not a full client
profile. A remote provider update must create or update one independent proxy
entry per item under the proxies list. Routing, DNS, listeners, groups and
dependency-bearing dialers therefore do not belong in this surface.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .singbox import ProxyNode, parse_proxy_uri


def _unique_name(base: str, seen: set[str]) -> str:
    """Return a stable unique Mihomo proxy name."""
    base = base.strip() or "proxy"
    candidate = base
    index = 1
    while candidate in seen:
        candidate = f"{base}-{index}"
        index += 1
    seen.add(candidate)
    return candidate


def _apply_transport(proxy: dict[str, Any], node: ProxyNode) -> bool:
    """Attach a representable V2Ray transport or reject a lossy mapping."""
    transport = node.transport_type
    if not transport:
        return True
    if transport == "ws":
        proxy["network"] = "ws"
        opts: dict[str, Any] = {}
        if node.transport_path:
            opts["path"] = node.transport_path
        if node.transport_host:
            opts["headers"] = {"Host": node.transport_host[0]}
        if opts:
            proxy["ws-opts"] = opts
        return True
    if transport == "grpc":
        proxy["network"] = "grpc"
        proxy["grpc-opts"] = {
            "grpc-service-name": node.transport_service_name or "grpc"
        }
        return True
    if transport == "http":
        proxy["network"] = "h2"
        opts = {}
        if node.transport_host:
            opts["host"] = node.transport_host
        if node.transport_path:
            opts["path"] = node.transport_path
        if opts:
            proxy["h2-opts"] = opts
        return True
    if transport == "httpupgrade":
        proxy["network"] = "httpupgrade"
        opts = {}
        if node.transport_host:
            opts["host"] = node.transport_host[0]
        if node.transport_path:
            opts["path"] = node.transport_path
        if opts:
            proxy["http-upgrade-opts"] = opts
        return True
    return False


def _apply_tls(proxy: dict[str, Any], node: ProxyNode, *, sni_key: str) -> None:
    """Attach Mihomo TLS and REALITY fields without profile-level policy."""
    if not node.tls_enabled:
        return
    proxy["tls"] = True
    server_name = node.tls_server_name or node.server
    if server_name:
        proxy[sni_key] = server_name
    if node.tls_insecure:
        proxy["skip-cert-verify"] = True
    if node.tls_alpn:
        proxy["alpn"] = list(node.tls_alpn)
    if node.tls_utls_fingerprint:
        proxy["client-fingerprint"] = node.tls_utls_fingerprint
    if node.tls_reality_public_key:
        proxy["reality-opts"] = {
            "public-key": node.tls_reality_public_key,
            "short-id": node.tls_reality_short_id,
        }


def _clash_proxy(node: ProxyNode, seen_names: set[str]) -> Optional[dict[str, Any]]:
    """Convert one normalized node into one independent Mihomo proxy mapping."""
    if node.realm_server_url:
        return None
    if not node.server or not 1 <= node.port <= 65535:
        return None

    name = _unique_name(node.tag or node.type, seen_names)
    common: dict[str, Any] = {
        "name": name,
        "server": node.server,
        "port": node.port,
    }

    if node.type == "vless":
        if not node.uuid:
            return None
        proxy = {
            **common,
            "type": "vless",
            "uuid": node.uuid,
            "udp": True,
        }
        if node.flow:
            proxy["flow"] = node.flow
        if node.packet_encoding:
            proxy["packet-encoding"] = node.packet_encoding
        if not _apply_transport(proxy, node):
            return None
        _apply_tls(proxy, node, sni_key="servername")
        return proxy

    if node.type == "vmess":
        if not node.uuid:
            return None
        proxy = {
            **common,
            "type": "vmess",
            "uuid": node.uuid,
            "alterId": node.alter_id,
            "cipher": node.security or "auto",
            "udp": True,
        }
        if not _apply_transport(proxy, node):
            return None
        _apply_tls(proxy, node, sni_key="servername")
        return proxy

    if node.type == "trojan":
        if not node.password:
            return None
        proxy = {
            **common,
            "type": "trojan",
            "password": node.password,
            "udp": True,
        }
        if not _apply_transport(proxy, node):
            return None
        _apply_tls(proxy, node, sni_key="sni")
        return proxy

    if node.type == "shadowsocks":
        if not node.method or not node.password or node.plugin:
            return None
        return {
            **common,
            "type": "ss",
            "cipher": node.method,
            "password": node.password,
            "udp": True,
        }

    if node.type == "hysteria2":
        if not node.password:
            return None
        proxy = {
            **common,
            "type": "hysteria2",
            "password": node.password,
        }
        if node.server_ports:
            proxy["ports"] = ",".join(node.server_ports)
        if node.up_mbps:
            proxy["up"] = f"{node.up_mbps} Mbps"
        if node.down_mbps:
            proxy["down"] = f"{node.down_mbps} Mbps"
        if node.obfs_type and node.obfs_password:
            proxy["obfs"] = node.obfs_type
            proxy["obfs-password"] = node.obfs_password
        _apply_tls(proxy, node, sni_key="sni")
        return proxy

    if node.type == "hysteria":
        if not node.password:
            return None
        proxy = {
            **common,
            "type": "hysteria",
            "auth-str": node.password,
        }
        if node.up_mbps:
            proxy["up"] = f"{node.up_mbps} Mbps"
        if node.down_mbps:
            proxy["down"] = f"{node.down_mbps} Mbps"
        if node.obfs_password:
            proxy["obfs"] = node.obfs_password
        _apply_tls(proxy, node, sni_key="sni")
        return proxy

    if node.type == "tuic":
        if not node.uuid or not node.password:
            return None
        proxy = {
            **common,
            "type": "tuic",
            "uuid": node.uuid,
            "password": node.password,
            "congestion-controller": node.congestion_control or "cubic",
            "udp-relay-mode": "native",
        }
        _apply_tls(proxy, node, sni_key="sni")
        return proxy

    if node.type == "anytls":
        if not node.password or node.tls_reality_public_key:
            return None
        proxy = {
            **common,
            "type": "anytls",
            "password": node.password,
            "udp": True,
        }
        _apply_tls(proxy, node, sni_key="sni")
        return proxy

    if node.type == "socks":
        proxy = {**common, "type": "socks5", "udp": True}
        if node.username:
            proxy["username"] = node.username
        if node.password:
            proxy["password"] = node.password
        return proxy

    if node.type == "http":
        proxy = {**common, "type": "http"}
        if node.username:
            proxy["username"] = node.username
        if node.password:
            proxy["password"] = node.password
        _apply_tls(proxy, node, sni_key="sni")
        return proxy

    return None


def build_clash_subscription_bytes(text: str) -> bytes:
    """Render a proxies-only Mihomo provider with independent entries."""
    seen_names: set[str] = set()
    proxies: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        node = parse_proxy_uri(line)
        if node is None:
            continue
        proxy = _clash_proxy(node, seen_names)
        if proxy is not None:
            proxies.append(proxy)
    if not proxies:
        return b""

    # JSON flow mappings are valid YAML 1.2 mappings. Keeping one proxy per
    # list item avoids a YAML dependency while safely quoting source strings.
    lines = ["proxies:"]
    lines.extend(
        "  - " + json.dumps(proxy, ensure_ascii=False, separators=(",", ":"))
        for proxy in proxies
    )
    return ("\n".join(lines) + "\n").encode("utf-8")
