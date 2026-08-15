# src/huntx/formats/common/singbox.py
"""Convert proxy URIs into a sing-box client configuration.

HuntX already decodes proxy URIs into structured JSON and re-encodes base64
subscriptions; this module adds a sing-box client-config output on top of that,
reusing the shared base64 decoder in :mod:`huntx.formats.common.b64` and
matching the repository's style.

The public entry point is :func:`build_singbox_config_bytes`, which turns a
newline-delimited block of proxy URIs into pretty-printed, UTF-8 encoded
sing-box configuration bytes suitable for use as a build derivative.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Optional

from .b64 import b64_decode


@dataclass
class ProxyNode:
    """Normalized proxy description independent of the source URI scheme."""

    type: str = ""
    tag: str = ""
    server: str = ""
    port: int = 0
    uuid: str = ""
    alter_id: int = 0
    security: str = "auto"
    method: str = ""
    password: str = ""
    plugin: str = ""
    plugin_opts: str = ""
    flow: str = ""
    network: str = "tcp"
    tls_enabled: bool = True
    tls_server_name: str = ""
    tls_insecure: bool = False
    tls_alpn: list = field(default_factory=list)
    tls_utls_fingerprint: str = ""
    tls_reality_enabled: bool = False
    tls_reality_public_key: str = ""
    tls_reality_short_id: str = ""
    transport_type: str = ""
    transport_path: str = ""
    transport_host: list = field(default_factory=list)
    transport_service_name: str = ""
    obfs_type: str = ""
    obfs_password: str = ""
    congestion_control: str = "cubic"
    up_mbps: int = 0
    down_mbps: int = 0
    packet_encoding: str = ""
    server_ports: list = field(default_factory=list)


def _safe_b64(value: str) -> str:
    """Best-effort base64 decode that never raises (returns "" on failure)."""
    try:
        return b64_decode(value)
    except Exception:
        return ""


def _full_unquote(value: str) -> str:
    """Percent-decode until the string is stable.

    Telegram-scraped remarks are frequently double- or triple-encoded
    (e.g. ``%2520`` for a space). A single :func:`urllib.parse.unquote`
    leaves the inner escapes intact, so repeat until the result no longer
    changes to recover the human-readable tag.
    """
    if "%" not in value:
        return value
    previous = ""
    while value != previous:
        previous = value
        value = urllib.parse.unquote(value)
    return value


def _parse_query(query: str) -> dict[str, str]:
    params: dict[str, str] = {}
    if not query:
        return params
    for part in query.split("&"):
        if "=" in part:
            key, value = part.split("=", 1)
            params[key] = urllib.parse.unquote(value)
    return params


def _split_hostport(hostport: str) -> Optional[tuple[str, int]]:
    if ":" not in hostport:
        return None
    host, _, port_s = hostport.rpartition(":")
    try:
        return host, int(port_s)
    except ValueError:
        return None


def _apply_transport(node: ProxyNode, transport: str, params: dict[str, str]) -> None:
    if transport == "ws":
        node.transport_type = "ws"
        node.transport_path = params.get("path", "")
        host = params.get("host", "")
        if host:
            node.transport_host = [host]
    elif transport == "grpc":
        node.transport_type = "grpc"
        node.transport_service_name = params.get("serviceName", "grpc")
    elif transport in ("h2", "http"):
        node.transport_type = "http"
        node.transport_path = params.get("path", "")
        host = params.get("host", "")
        if host:
            node.transport_host = [h.strip() for h in host.split(",")]
    elif transport == "httpupgrade":
        node.transport_type = "httpupgrade"
        node.transport_path = params.get("path", "")
        host = params.get("host", "")
        if host:
            node.transport_host = [host]
    elif transport == "quic":
        node.transport_type = "quic"


def _parse_vmess(url: str) -> Optional[ProxyNode]:
    raw = url[len("vmess://") :]
    decoded = _safe_b64(raw)
    if not decoded:
        return None
    try:
        data = json.loads(decoded)
    except (ValueError, TypeError):
        return None

    node = ProxyNode(type="vmess")
    node.tag = data.get("ps", "") or data.get("add", "vmess")
    node.server = data.get("add", "")
    try:
        node.port = int(data.get("port", 0))
        node.alter_id = int(data.get("aid", 0))
    except (ValueError, TypeError):
        return None
    node.uuid = data.get("id", "")
    node.security = data.get("scy", "auto") or "auto"
    node.network = data.get("net", "tcp") or "tcp"

    node.tls_enabled = data.get("tls", "") == "tls"
    node.tls_server_name = data.get("sni", "") or data.get("host", "")
    node.tls_insecure = str(data.get("allowInsecure", "0")) == "1"

    host = data.get("host", "")
    path = data.get("path", "")
    net = node.network
    if net == "ws":
        node.transport_type = "ws"
        node.transport_path = path
        if host:
            node.transport_host = [host]
    elif net == "grpc":
        node.transport_type = "grpc"
        node.transport_service_name = path or "grpc"
    elif net in ("h2", "http"):
        node.transport_type = "http"
        node.transport_path = path
        if host:
            node.transport_host = [host] if isinstance(host, str) else host
    elif net == "quic":
        node.transport_type = "quic"

    if not node.tls_server_name and host:
        node.tls_server_name = host
    return node


def _parse_userinfo_scheme(url: str, scheme: str, node_type: str) -> Optional[ProxyNode]:
    """Shared parser for ``scheme://userinfo@host:port?params#tag`` URIs."""
    node = ProxyNode(type=node_type)
    raw = url[len(scheme) :]
    main, _, fragment = raw.partition("#")
    node.tag = _full_unquote(fragment) if fragment else node_type

    userinfo, _, hostinfo = main.partition("@")
    userinfo = urllib.parse.unquote(userinfo)
    if node_type == "vless":
        node.uuid = userinfo
    else:
        node.password = userinfo

    hostport, _, query = hostinfo.partition("?")
    hostport_result = _split_hostport(hostport)
    if hostport_result is None:
        return None
    node.server, node.port = hostport_result

    params = _parse_query(query)
    node.flow = params.get("flow", "")
    node.security = params.get("security", "tls")
    if node_type == "vless":
        node.tls_enabled = node.security in ("tls", "reality")
    else:
        node.tls_enabled = node.security == "tls"
    node.tls_server_name = params.get("sni", "") or params.get("host", "")
    node.tls_insecure = params.get("allowInsecure", "0") == "1"

    fingerprint = params.get("fp", "")
    if fingerprint:
        node.tls_utls_fingerprint = fingerprint
    if params.get("pbk"):
        node.tls_reality_enabled = True
        node.tls_reality_public_key = params.get("pbk", "")
        node.tls_reality_short_id = params.get("sid", "")
    alpn = params.get("alpn", "")
    if alpn:
        node.tls_alpn = alpn.split(",")

    transport = params.get("type", "tcp") or "tcp"
    node.network = transport
    _apply_transport(node, transport, params)
    node.packet_encoding = params.get("packetEncoding", "xudp")
    if not node.tls_server_name:
        node.tls_server_name = params.get("host", "")
    return node


def _parse_shadowsocks(url: str) -> Optional[ProxyNode]:
    node = ProxyNode(type="shadowsocks")
    raw = url[len("ss://") :]
    main, _, fragment = raw.partition("#")
    node.tag = _full_unquote(fragment) if fragment else "ss"

    hostport = ""
    query = ""
    if "@" in main:
        userinfo, _, hostinfo = main.partition("@")
        decoded = urllib.parse.unquote(userinfo)
        decoded = _safe_b64(decoded) or decoded
        if ":" in decoded:
            node.method, node.password = decoded.split(":", 1)
        else:
            node.method = decoded
        hostport, _, query = hostinfo.partition("?")
    else:
        decoded = _safe_b64(urllib.parse.unquote(main.split("?", 1)[0]))
        if not decoded:
            return None
        if "@" in decoded:
            userinfo, _, hostport = decoded.partition("@")
            if ":" in userinfo:
                node.method, node.password = userinfo.split(":", 1)
            else:
                node.method = userinfo
            if "?" in main:
                _, query = main.rsplit("?", 1)
        else:
            try:
                return _parse_shadowsocks_json(json.loads(decoded), node.tag)
            except (ValueError, TypeError):
                return None

    hostport_result = _split_hostport(hostport)
    if hostport_result is None:
        return None
    node.server, node.port = hostport_result

    params = _parse_query(query)
    plugin = params.get("plugin", "")
    if plugin:
        node.plugin = plugin
        node.plugin_opts = params.get("plugin-opts", "")
    return node


def _parse_shadowsocks_json(data: dict, tag: str = "ss") -> Optional[ProxyNode]:
    """Build a shadowsocks node from a decoded JSON payload (SIP008 form)."""
    node = ProxyNode(type="shadowsocks")
    node.tag = tag
    node.server = data.get("server", "")
    try:
        node.port = int(data.get("server_port", 0))
    except (ValueError, TypeError):
        return None
    node.method = data.get("method", "")
    node.password = data.get("password", "")
    node.plugin = data.get("plugin", "")
    node.plugin_opts = data.get("plugin_opts", "")
    return node


def _parse_hysteria2(url: str) -> Optional[ProxyNode]:
    node = ProxyNode(type="hysteria2")
    raw = url.replace("hysteria2://", "").replace("hy2://", "")
    main, _, fragment = raw.partition("#")
    node.tag = _full_unquote(fragment) if fragment else "hy2"

    userinfo, _, hostinfo = main.partition("@")
    node.password = urllib.parse.unquote(userinfo)
    hostport, _, query = hostinfo.partition("?")
    hostport_result = _split_hostport(hostport)
    if hostport_result is None:
        return None
    node.server, node.port = hostport_result

    params = _parse_query(query)
    node.tls_enabled = True
    node.tls_server_name = params.get("sni", "")
    node.tls_insecure = params.get("insecure", "0") == "1"
    obfs = params.get("obfs-password", "") or params.get("obfs", "")
    if obfs:
        node.obfs_type = "salamander"
        node.obfs_password = obfs
    alpn = params.get("alpn", "")
    if alpn:
        node.tls_alpn = alpn.split(",")
    _apply_bandwidth(node, params)
    return node


def _parse_hysteria(url: str) -> Optional[ProxyNode]:
    """Parse legacy ``hysteria://`` (v1) URIs into a :class:`ProxyNode`."""
    node = ProxyNode(type="hysteria")
    raw = url[len("hysteria://") :]
    main, _, fragment = raw.partition("#")
    node.tag = _full_unquote(fragment) if fragment else "hysteria"

    userinfo, sep, hostinfo = main.partition("@")
    if not sep:
        hostinfo = userinfo
    else:
        node.password = urllib.parse.unquote(userinfo)
    hostport, _, query = hostinfo.partition("?")
    hostport_result = _split_hostport(hostport)
    if hostport_result is None:
        return None
    node.server, node.port = hostport_result

    params = _parse_query(query)
    if not node.password:
        node.password = params.get("auth", "") or params.get("auth_str", "")
    node.tls_enabled = True
    node.tls_server_name = params.get("peer", "") or params.get("sni", "")
    node.tls_insecure = params.get("insecure", "0") == "1"
    obfs = params.get("obfs", "")
    if obfs:
        node.obfs_password = obfs
    alpn = params.get("alpn", "")
    if alpn:
        node.tls_alpn = alpn.split(",")
    _apply_bandwidth(node, params)
    return node


def _apply_bandwidth(node: ProxyNode, params: dict[str, str]) -> None:
    """Populate up/down Mbps and multi-port fields from query parameters."""
    up = params.get("up_mbps", "") or params.get("up", "")
    down = params.get("down_mbps", "") or params.get("down", "")
    if up:
        try:
            node.up_mbps = int("".join(c for c in up if c.isdigit()) or 0)
        except ValueError:
            pass
    if down:
        try:
            node.down_mbps = int("".join(c for c in down if c.isdigit()) or 0)
        except ValueError:
            pass
    ports = params.get("mport", "") or params.get("ports", "")
    if ports:
        node.server_ports = [ports]


def _parse_tuic(url: str) -> Optional[ProxyNode]:
    node = ProxyNode(type="tuic")
    raw = url[len("tuic://") :]
    main, _, fragment = raw.partition("#")
    node.tag = _full_unquote(fragment) if fragment else "tuic"

    userinfo, _, hostinfo = main.partition("@")
    userinfo = urllib.parse.unquote(userinfo)
    if ":" in userinfo:
        node.uuid, node.password = userinfo.split(":", 1)
    else:
        node.uuid = userinfo

    hostport, _, query = hostinfo.partition("?")
    hostport_result = _split_hostport(hostport)
    if hostport_result is None:
        return None
    node.server, node.port = hostport_result

    params = _parse_query(query)
    if params.get("password") and not node.password:
        node.password = params["password"]
    node.congestion_control = params.get("congestion_control", "cubic")
    node.tls_enabled = True
    node.tls_server_name = params.get("sni", "")
    node.tls_insecure = params.get("allowInsecure", "0") == "1"
    alpn = params.get("alpn", "")
    if alpn:
        node.tls_alpn = alpn.split(",")
    return node


def _parse_wireguard(url: str) -> Optional[ProxyNode]:
    node = ProxyNode(type="wireguard")
    scheme_len = len("wireguard://") if url.startswith("wireguard://") else len("wg://")
    raw = url[scheme_len:]
    main, _, fragment = raw.partition("#")
    node.tag = _full_unquote(fragment) if fragment else "wg"

    hostpart, _, query = main.partition("?")
    if "@" in hostpart:
        node.uuid, _, host_port = hostpart.partition("@")
        hostport_result = _split_hostport(host_port)
        if hostport_result is not None:
            node.server, node.port = hostport_result

    params = _parse_query(query)
    if params.get("privateKey"):
        node.password = params["privateKey"]
    if params.get("peerPublicKey"):
        node.uuid = params["peerPublicKey"]
    return node


def _parse_anytls(url: str) -> Optional[ProxyNode]:
    """Parse ``anytls://password@host:port?params#tag`` URIs."""
    node = ProxyNode(type="anytls")
    raw = url[len("anytls://") :]
    main, _, fragment = raw.partition("#")
    node.tag = _full_unquote(fragment) if fragment else "anytls"

    userinfo, _, hostinfo = main.partition("@")
    node.password = urllib.parse.unquote(userinfo)
    hostport, _, query = hostinfo.partition("?")
    hostport_result = _split_hostport(hostport)
    if hostport_result is None:
        return None
    node.server, node.port = hostport_result

    params = _parse_query(query)
    node.security = params.get("security", "tls")
    node.tls_enabled = node.security != "none"
    node.tls_server_name = params.get("sni", "") or params.get("host", "")
    node.tls_insecure = params.get("insecure", "0") == "1" or params.get("allowInsecure", "0") == "1"
    fingerprint = params.get("fp", "")
    if fingerprint:
        node.tls_utls_fingerprint = fingerprint
    alpn = params.get("alpn", "")
    if alpn:
        node.tls_alpn = alpn.split(",")
    return node


def parse_proxy_uri(uri: str) -> Optional[ProxyNode]:
    """Parse a single proxy URI into a :class:`ProxyNode`, or ``None``."""
    uri = uri.strip()
    if uri.startswith("vmess://"):
        return _parse_vmess(uri)
    if uri.startswith("vless://"):
        return _parse_userinfo_scheme(uri, "vless://", "vless")
    if uri.startswith("trojan://"):
        return _parse_userinfo_scheme(uri, "trojan://", "trojan")
    if uri.startswith("ss://"):
        return _parse_shadowsocks(uri)
    if uri.startswith("hysteria2://") or uri.startswith("hy2://"):
        return _parse_hysteria2(uri)
    if uri.startswith("hysteria://"):
        return _parse_hysteria(uri)
    if uri.startswith("tuic://"):
        return _parse_tuic(uri)
    if uri.startswith("anytls://"):
        return _parse_anytls(uri)
    if uri.startswith("wireguard://") or uri.startswith("wg://"):
        return _parse_wireguard(uri)
    # juicity:// has no native sing-box outbound type, so it is intentionally
    # not converted here; it still passes through the raw/base64 derivatives.
    return None


def _build_tls(node: ProxyNode) -> dict[str, Any]:
    tls: dict[str, Any] = {}
    if not node.tls_enabled:
        return tls
    tls["enabled"] = True
    if node.tls_server_name:
        tls["server_name"] = node.tls_server_name
    if node.tls_insecure:
        tls["insecure"] = True
    if node.tls_alpn:
        tls["alpn"] = node.tls_alpn
    if node.tls_utls_fingerprint:
        tls["utls"] = {"enabled": True, "fingerprint": node.tls_utls_fingerprint}
    if node.tls_reality_enabled:
        tls["reality"] = {
            "enabled": True,
            "public_key": node.tls_reality_public_key,
            "short_id": node.tls_reality_short_id,
        }
    return tls


def _build_transport(node: ProxyNode) -> dict[str, Any]:
    transport: dict[str, Any] = {}
    if not node.transport_type:
        return transport
    transport["type"] = node.transport_type
    if node.transport_type == "ws":
        if node.transport_path:
            transport["path"] = node.transport_path
        if node.transport_host:
            transport["headers"] = {"Host": node.transport_host[0]}
    elif node.transport_type == "grpc":
        transport["service_name"] = node.transport_service_name or "grpc"
    elif node.transport_type == "http":
        if node.transport_host:
            transport["host"] = node.transport_host
        if node.transport_path:
            transport["path"] = node.transport_path
    elif node.transport_type == "httpupgrade":
        if node.transport_host:
            transport["host"] = node.transport_host[0]
        if node.transport_path:
            transport["path"] = node.transport_path
    return transport


def build_outbound(node: ProxyNode) -> dict[str, Any]:
    """Build one sing-box outbound object from a :class:`ProxyNode`."""
    ob: dict[str, Any] = {
        "type": node.type,
        "tag": node.tag,
        "server": node.server,
        "server_port": node.port,
    }

    if node.type == "vmess":
        ob["uuid"] = node.uuid
        ob["security"] = node.security
        ob["alter_id"] = node.alter_id
        ob["global_padding"] = False
        ob["authenticated_length"] = True
        ob["network"] = node.network
        ob["packet_encoding"] = node.packet_encoding or ""
    elif node.type == "vless":
        ob["uuid"] = node.uuid
        if node.flow:
            ob["flow"] = node.flow
        ob["network"] = node.network
        ob["packet_encoding"] = node.packet_encoding or "xudp"
    elif node.type == "trojan":
        ob["password"] = node.password
        ob["network"] = node.network
    elif node.type == "shadowsocks":
        ob["method"] = node.method
        ob["password"] = node.password
        ob["network"] = node.network or "tcp"
        if node.plugin:
            ob["plugin"] = node.plugin
            ob["plugin_opts"] = node.plugin_opts
    elif node.type == "hysteria2":
        ob["password"] = node.password
        if node.up_mbps:
            ob["up_mbps"] = node.up_mbps
        if node.down_mbps:
            ob["down_mbps"] = node.down_mbps
        if node.obfs_type:
            ob["obfs"] = {"type": node.obfs_type, "password": node.obfs_password}
        if node.server_ports:
            ob["server_ports"] = node.server_ports
    elif node.type == "hysteria":
        ob["auth_str"] = node.password
        if node.up_mbps:
            ob["up_mbps"] = node.up_mbps
        if node.down_mbps:
            ob["down_mbps"] = node.down_mbps
        if node.obfs_password:
            ob["obfs"] = node.obfs_password
    elif node.type == "tuic":
        ob["uuid"] = node.uuid
        if node.password:
            ob["password"] = node.password
        ob["congestion_control"] = node.congestion_control
        ob["udp_relay_mode"] = "native"
        ob["zero_rtt_handshake"] = False
        ob["heartbeat"] = "10s"
    elif node.type == "wireguard":
        ob["local_address"] = ["10.0.0.2/32"]
        ob["private_key"] = node.password
        ob["peer_public_key"] = node.uuid
        ob["reserved"] = [0, 0, 0]
        ob["mtu"] = 1408
    elif node.type == "anytls":
        ob["password"] = node.password
        ob["idle_session_check_interval"] = "30s"
        ob["idle_session_timeout"] = "30s"

    tls = _build_tls(node)
    if node.type in ("hysteria2", "hysteria", "tuic"):
        ob["tls"] = tls or {"enabled": True}
    elif tls:
        ob["tls"] = tls

    transport = _build_transport(node)
    if transport and node.type in ("vmess", "vless", "trojan"):
        ob["transport"] = transport
    return ob


def build_singbox_config(
    outbounds: list[dict[str, Any]],
    *,
    listen: str = "127.0.0.1",
    mixed_port: int = 2080,
    tun_enabled: bool = False,
    experimental: bool = True,
) -> dict[str, Any]:
    """Assemble a full sing-box client config around the given outbounds."""
    proxy_tags = [ob["tag"] for ob in outbounds]
    auto_outbounds = [t for t in proxy_tags if t not in ("direct", "block", "dns-out")]

    config: dict[str, Any] = {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [
                {"tag": "google", "address": "tls://8.8.8.8", "detour": "select"},
                {"tag": "local", "address": "223.5.5.5", "detour": "direct"},
            ],
            "rules": [{"outbound": ["any"], "server": "local"}],
            "final": "google",
            "strategy": "prefer_ipv4",
            "optimistic": True,
            "reverse_mapping": True,
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": listen,
                "listen_port": mixed_port,
                "set_system_proxy": False,
            }
        ],
        "outbounds": [
            {
                "type": "selector",
                "tag": "select",
                "outbounds": ["auto"] + auto_outbounds + ["direct"],
                "default": "auto",
            }
        ]
        + outbounds
        + [
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
            {"type": "dns", "tag": "dns-out"},
        ],
        "route": {
            "rules": [
                {"ip_is_private": True, "outbound": "direct"},
                {"protocol": "dns", "action": "hijack-dns"},
                {"action": "route", "outbound": "select"},
            ],
            "final": "select",
            "auto_detect_interface": True,
        },
    }

    if auto_outbounds:
        config["outbounds"].insert(
            1,
            {
                "type": "urltest",
                "tag": "auto",
                "outbounds": auto_outbounds,
                "url": "https://www.gstatic.com/generate_204",
                "interval": "3m",
                "tolerance": 50,
                "idle_timeout": "30m",
            },
        )

    if tun_enabled:
        config["inbounds"].insert(
            0,
            {
                "type": "tun",
                "tag": "tun-in",
                "address": ["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
                "mtu": 9000,
                "auto_route": True,
                "strict_route": True,
                "stack": "system",
                "dns_mode": "hijack",
                "dns_address": ["172.19.0.2", "fdfe:dcba:9876::2"],
            },
        )

    if experimental:
        config["experimental"] = {
            "cache_file": {"enabled": True, "path": "cache.db", "store_dns": True},
            "clash_api": {
                "external_controller": "127.0.0.1:9090",
                "access_control_allow_origin": ["*"],
                "access_control_allow_private_network": True,
            },
        }
    return config


def config_from_uris(
    uris: list[str],
    *,
    listen: str = "127.0.0.1",
    mixed_port: int = 2080,
    tun_enabled: bool = False,
) -> dict[str, Any]:
    """Parse proxy URIs and assemble a sing-box config with unique tags."""
    outbounds: list[dict[str, Any]] = []
    seen_tags: set[str] = set()
    for uri in uris:
        uri = uri.strip()
        if not uri or uri.startswith("#"):
            continue
        node = parse_proxy_uri(uri)
        if node is None:
            continue
        ob = build_outbound(node)
        base_tag = ob["tag"] or node.type
        tag = base_tag
        counter = 1
        while tag in seen_tags:
            tag = f"{base_tag}-{counter}"
            counter += 1
        ob["tag"] = tag
        seen_tags.add(tag)
        outbounds.append(ob)

    return build_singbox_config(
        outbounds,
        listen=listen,
        mixed_port=mixed_port,
        tun_enabled=tun_enabled,
    )


def build_singbox_config_bytes(text: str) -> bytes:
    """Build sing-box config bytes from newline-delimited proxy URIs.

    Returns empty bytes when no proxy URI parses, so callers can skip emitting
    an empty derivative artifact.
    """
    try:
        lines = text.splitlines()
    except AttributeError:
        return b""
    config = config_from_uris(lines)
    proxy_outbounds = [
        ob
        for ob in config.get("outbounds", [])
        if ob.get("type") not in ("selector", "urltest", "direct", "block", "dns")
    ]
    if not proxy_outbounds:
        return b""
    return json.dumps(config, indent=2, ensure_ascii=False).encode("utf-8")
