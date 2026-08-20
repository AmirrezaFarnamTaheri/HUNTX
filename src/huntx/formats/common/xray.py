"""Render supported proxy share URIs as a current Xray client configuration."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any, Optional

from .b64 import b64_decode
from .singbox import ProxyNode, parse_proxy_uri

_XRAY_TRANSPORT_METHODS = {
    "": "raw",
    "ws": "websocket",
    "grpc": "grpc",
    "httpupgrade": "httpupgrade",
}


def _unique_tag(base: str, seen: set[str]) -> str:
    """Return a stable unique Xray outbound tag."""
    base = base.strip() or "proxy"
    candidate = base
    index = 1
    while candidate in seen:
        candidate = f"{base}-{index}"
        index += 1
    seen.add(candidate)
    return candidate


def _declared_transport_is_representable(uri: str, node: ProxyNode) -> bool:
    """Reject share transports the normalized node cannot preserve losslessly."""
    lower = uri.lower()
    transport = "tcp"
    header_type = ""

    if lower.startswith("vmess://"):
        try:
            data = json.loads(b64_decode(uri[len("vmess://") :]))
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        transport = str(data.get("net", "tcp") or "tcp").lower()
        header_type = str(data.get("type", "") or "").lower()
    elif lower.startswith(("vless://", "trojan://")):
        try:
            parsed = urllib.parse.urlsplit(uri)
            params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        except ValueError:
            return False
        if lower.startswith("vless://") and "encryption" in params:
            encryption = str(params["encryption"] or "").lower()
            if encryption != "none":
                return False
        transport = str(params.get("type", "tcp") or "tcp").lower()
        header_type = str(
            params.get("headerType", "") or params.get("header_type", "") or ""
        ).lower()
    else:
        return True

    if transport in {"", "tcp", "raw"}:
        return header_type in {"", "none"} and not node.transport_type

    expected_node_transport = {
        "ws": "ws",
        "grpc": "grpc",
        "httpupgrade": "httpupgrade",
    }.get(transport)
    return expected_node_transport is not None and node.transport_type == expected_node_transport


def _tls_settings(node: ProxyNode) -> dict[str, Any]:
    """Build Xray TLS settings from one normalized proxy node."""
    tls: dict[str, Any] = {}
    if node.tls_server_name:
        tls["serverName"] = node.tls_server_name
    if node.tls_insecure:
        tls["allowInsecure"] = True
    if node.tls_alpn:
        tls["alpn"] = node.tls_alpn
    if node.tls_utls_fingerprint:
        tls["fingerprint"] = node.tls_utls_fingerprint
    return tls


def _stream_settings(node: ProxyNode) -> Optional[dict[str, Any]]:
    """Build current Xray streamSettings or reject lossy transport mappings."""
    if node.type == "hysteria2":
        if node.realm_server_url or node.server_ports or node.obfs_type:
            return None
        stream: dict[str, Any] = {
            "method": "hysteria",
            "security": "tls",
            "hysteriaSettings": {"version": 2, "auth": node.password},
            "tlsSettings": _tls_settings(node),
        }
        return stream

    method = _XRAY_TRANSPORT_METHODS.get(node.transport_type)
    if method is None:
        return None
    if node.tls_reality_enabled and method not in {"raw", "grpc"}:
        return None

    stream = {"method": method, "security": "none"}
    if method == "websocket":
        settings: dict[str, Any] = {}
        if node.transport_path:
            settings["path"] = node.transport_path
        if node.transport_host:
            settings["host"] = node.transport_host[0]
        if settings:
            stream["wsSettings"] = settings
    elif method == "grpc":
        settings = {}
        if node.transport_service_name:
            settings["serviceName"] = node.transport_service_name
        if settings:
            stream["grpcSettings"] = settings
    elif method == "httpupgrade":
        settings = {}
        if node.transport_path:
            settings["path"] = node.transport_path
        if node.transport_host:
            settings["host"] = node.transport_host[0]
        if settings:
            stream["httpupgradeSettings"] = settings

    if node.tls_reality_enabled:
        reality = {
            "serverName": node.tls_server_name or node.server,
            "fingerprint": node.tls_utls_fingerprint or "chrome",
            "password": node.tls_reality_public_key,
            "shortId": node.tls_reality_short_id,
        }
        stream["security"] = "reality"
        stream["realitySettings"] = reality
    elif node.tls_enabled:
        stream["security"] = "tls"
        stream["tlsSettings"] = _tls_settings(node)
    return stream


def _protocol_settings(node: ProxyNode) -> Optional[tuple[str, dict[str, Any]]]:
    """Map a normalized proxy node to a current Xray outbound protocol/settings pair."""
    if node.type == "vmess" and node.server and node.uuid and node.port:
        return (
            "vmess",
            {
                "address": node.server,
                "port": node.port,
                "id": node.uuid,
                "security": node.security or "auto",
            },
        )
    if node.type == "vless" and node.server and node.uuid and node.port:
        settings: dict[str, Any] = {
            "address": node.server,
            "port": node.port,
            "id": node.uuid,
            "encryption": "none",
        }
        if node.flow:
            settings["flow"] = node.flow
        return "vless", settings
    if node.type == "trojan" and node.server and node.password and node.port:
        return (
            "trojan",
            {"address": node.server, "port": node.port, "password": node.password},
        )
    if node.type == "shadowsocks" and node.server and node.method and node.password and node.port:
        if node.plugin:
            return None
        return (
            "shadowsocks",
            {
                "address": node.server,
                "port": node.port,
                "method": node.method,
                "password": node.password,
            },
        )
    if node.type == "socks" and node.server and node.port:
        if node.version not in {"", "5"}:
            return None
        settings = {"address": node.server, "port": node.port}
        if node.username:
            settings["user"] = node.username
        if node.password:
            settings["pass"] = node.password
        return "socks", settings
    if node.type == "http" and node.server and node.port:
        settings = {"address": node.server, "port": node.port}
        if node.username:
            settings["user"] = node.username
        if node.password:
            settings["pass"] = node.password
        return "http", settings
    if node.type == "hysteria2" and node.server and node.password and node.port:
        if node.realm_server_url or node.server_ports or node.obfs_type:
            return None
        return (
            "hysteria",
            {"version": 2, "address": node.server, "port": node.port},
        )
    return None


def _outbound(node: ProxyNode, tag: str) -> Optional[dict[str, Any]]:
    """Render one normalized node as a lossless current Xray outbound."""
    protocol_settings = _protocol_settings(node)
    if protocol_settings is None:
        return None
    stream_settings = _stream_settings(node)
    if stream_settings is None:
        return None
    protocol, settings = protocol_settings
    return {
        "tag": tag,
        "protocol": protocol,
        "settings": settings,
        "streamSettings": stream_settings,
    }


def proxy_outbounds_from_uris(uris: list[str]) -> list[dict[str, Any]]:
    """Convert representable share URIs into unique-tagged Xray proxy outbounds."""
    outbounds: list[dict[str, Any]] = []
    seen_tags = {"direct", "socks-in"}
    for uri in uris:
        uri = uri.strip()
        if not uri or uri.startswith("#"):
            continue
        node = parse_proxy_uri(uri)
        if node is None or not _declared_transport_is_representable(uri, node):
            continue
        tag = _unique_tag(node.tag or node.type, seen_tags)
        outbound = _outbound(node, tag)
        if outbound is not None:
            outbounds.append(outbound)
    return outbounds


def build_xray_config(outbounds: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a complete Xray client config with a local SOCKS inbound."""
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks-in",
                "listen": "127.0.0.1",
                "port": 10808,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
            }
        ],
        "outbounds": outbounds
        + [{"tag": "direct", "protocol": "freedom", "settings": {}}],
    }


def build_xray_config_bytes(text: str) -> bytes:
    """Render proxy text as UTF-8 Xray JSON, or empty bytes if nothing maps safely."""
    try:
        outbounds = proxy_outbounds_from_uris(text.splitlines())
    except AttributeError:
        return b""
    if not outbounds:
        return b""
    return json.dumps(
        build_xray_config(outbounds),
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")
