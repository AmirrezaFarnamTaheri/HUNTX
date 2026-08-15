# src/huntx/formats/common/singbox.py
"""Render proxy URIs as a sing-box 1.14+ client configuration.

The renderer targets the current sing-box schema. Legacy protocols that no
longer have a native outbound (for example Hysteria v1 and WireGuard outbound)
are deliberately skipped instead of emitting configuration rejected by modern
sing-box releases.
"""
from __future__ import annotations

import ipaddress
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Optional

from .b64 import b64_decode

TARGET_SINGBOX_VERSION = "1.14+"
_RESERVED_TAGS = {"select", "auto", "direct"}
_SUPPORTED_HY2_OBFS = {"salamander", "gecko"}


@dataclass
class ProxyNode:
    type: str
    tag: str
    server: str
    port: int
    uuid: str = ""
    password: str = ""
    method: str = ""
    alter_id: int = 0
    security: str = "auto"
    flow: str = ""
    network: str = ""
    packet_encoding: str = ""
    plugin: str = ""
    plugin_opts: str = ""
    tls_enabled: bool = False
    tls_server_name: str = ""
    tls_insecure: bool = False
    tls_alpn: list[str] = field(default_factory=list)
    tls_utls_fingerprint: str = ""
    tls_reality_public_key: str = ""
    tls_reality_short_id: str = ""
    transport_type: str = ""
    transport_path: str = ""
    transport_host: list[str] = field(default_factory=list)
    transport_service_name: str = ""
    obfs_type: str = ""
    obfs_password: str = ""
    congestion_control: str = "cubic"
    up_mbps: int = 0
    down_mbps: int = 0
    server_ports: list[str] = field(default_factory=list)

    @property
    def tls_reality_enabled(self) -> bool:
        """Compatibility accessor for the feature branch's original parser API."""
        return bool(self.tls_reality_public_key)


def _safe_b64(value: str) -> str:
    try:
        return b64_decode(value)
    except Exception:
        return ""


def _full_unquote(value: str) -> str:
    previous = None
    while "%" in value and value != previous:
        previous = value
        value = urllib.parse.unquote(value)
    return value


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parsed_url(uri: str) -> Optional[urllib.parse.SplitResult]:
    try:
        parsed = urllib.parse.urlsplit(uri)
        if not parsed.hostname or parsed.port is None or not 1 <= parsed.port <= 65535:
            return None
        return parsed
    except ValueError:
        return None


def _query(parsed: urllib.parse.SplitResult) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _bandwidth(value: str) -> int:
    match = re.search(r"\d+", value or "")
    return int(match.group(0)) if match else 0


def _apply_tls(node: ProxyNode, params: dict[str, str], *, default_enabled: bool = False) -> None:
    security = params.get("security", "")
    node.tls_enabled = default_enabled or security in {"tls", "reality"}
    node.tls_server_name = params.get("sni", "") or params.get("peer", "") or params.get("host", "")
    node.tls_insecure = params.get("insecure", "0") == "1" or params.get("allowInsecure", "0") == "1"
    node.tls_utls_fingerprint = params.get("fp", "")
    if params.get("alpn"):
        node.tls_alpn = [part.strip() for part in params["alpn"].split(",") if part.strip()]
    if security == "reality" or params.get("pbk"):
        node.tls_enabled = True
        node.tls_reality_public_key = params.get("pbk", "")
        node.tls_reality_short_id = params.get("sid", "")


def _apply_transport(node: ProxyNode, params: dict[str, str], transport: str) -> None:
    if transport == "ws":
        node.transport_type = "ws"
        node.transport_path = params.get("path", "")
        if params.get("host"):
            node.transport_host = [params["host"]]
    elif transport == "grpc":
        node.transport_type = "grpc"
        node.transport_service_name = params.get("serviceName", "") or params.get("service_name", "") or "grpc"
    elif transport in {"h2", "http"}:
        node.transport_type = "http"
        node.transport_path = params.get("path", "")
        if params.get("host"):
            node.transport_host = [part.strip() for part in params["host"].split(",") if part.strip()]
    elif transport == "httpupgrade":
        node.transport_type = "httpupgrade"
        node.transport_path = params.get("path", "")
        if params.get("host"):
            node.transport_host = [params["host"]]
    elif transport == "quic":
        node.transport_type = "quic"


def _parse_vmess(uri: str) -> Optional[ProxyNode]:
    decoded = _safe_b64(uri[len("vmess://") :])
    if not decoded:
        return None
    try:
        data = json.loads(decoded)
    except (TypeError, ValueError):
        return None
    server = str(data.get("add", "")).strip()
    port = _parse_int(data.get("port"))
    uuid = str(data.get("id", "")).strip()
    if not server or not uuid or not 1 <= port <= 65535:
        return None
    node = ProxyNode(
        type="vmess",
        tag=str(data.get("ps", "") or server),
        server=server,
        port=port,
        uuid=uuid,
        alter_id=max(0, _parse_int(data.get("aid"))),
        security=str(data.get("scy", "auto") or "auto"),
        packet_encoding=str(data.get("packetEncoding", "") or ""),
        tls_enabled=data.get("tls", "") == "tls",
        tls_server_name=str(data.get("sni", "") or data.get("host", "") or ""),
        tls_insecure=str(data.get("allowInsecure", "0")) == "1",
    )
    if data.get("alpn"):
        node.tls_alpn = [part.strip() for part in str(data["alpn"]).split(",") if part.strip()]
    transport_params = {
        "path": str(data.get("path", "") or ""),
        "host": str(data.get("host", "") or ""),
        "serviceName": str(data.get("serviceName", "") or data.get("path", "") or ""),
    }
    _apply_transport(node, transport_params, str(data.get("net", "tcp") or "tcp").lower())
    return node


def _parse_vless_or_trojan(uri: str, node_type: str) -> Optional[ProxyNode]:
    parsed = _parsed_url(uri)
    if parsed is None or not parsed.username:
        return None
    params = _query(parsed)
    credential = urllib.parse.unquote(parsed.username)
    node = ProxyNode(
        type=node_type,
        tag=_full_unquote(parsed.fragment) or node_type,
        server=parsed.hostname or "",
        port=parsed.port or 0,
        uuid=credential if node_type == "vless" else "",
        password=credential if node_type == "trojan" else "",
        flow=params.get("flow", "") if node_type == "vless" else "",
        packet_encoding=(params.get("packetEncoding", "") or params.get("packet_encoding", "") or "xudp")
        if node_type == "vless"
        else "",
    )
    if params.get("network") in {"tcp", "udp"}:
        node.network = params["network"]
    _apply_tls(node, params, default_enabled=node_type == "trojan" and params.get("security", "tls") != "none")
    _apply_transport(node, params, params.get("type", "tcp").lower())
    return node


def _parse_shadowsocks_json(data: dict[str, Any], tag: str) -> Optional[ProxyNode]:
    server = str(data.get("server", "")).strip()
    port = _parse_int(data.get("server_port"))
    method = str(data.get("method", "")).strip()
    password = str(data.get("password", ""))
    if not server or not method or not password or not 1 <= port <= 65535:
        return None
    return ProxyNode(
        type="shadowsocks",
        tag=tag or "ss",
        server=server,
        port=port,
        method=method,
        password=password,
        plugin=str(data.get("plugin", "") or ""),
        plugin_opts=str(data.get("plugin_opts", "") or ""),
    )


def _parse_shadowsocks(uri: str) -> Optional[ProxyNode]:
    raw = uri[len("ss://") :]
    main, _, fragment = raw.partition("#")
    tag = _full_unquote(fragment) or "ss"
    if "@" in main:
        userinfo, _, hostinfo = main.partition("@")
        decoded = urllib.parse.unquote(userinfo)
        decoded = _safe_b64(decoded) or decoded
        if ":" not in decoded:
            return None
        method, password = decoded.split(":", 1)
        hostport, _, query = hostinfo.partition("?")
        parsed = _parsed_url(f"ss://x@{hostport}")
    else:
        encoded, _, query = main.partition("?")
        decoded = _safe_b64(urllib.parse.unquote(encoded))
        if not decoded:
            return None
        if decoded.lstrip().startswith("{"):
            try:
                return _parse_shadowsocks_json(json.loads(decoded), tag)
            except (TypeError, ValueError):
                return None
        if "@" not in decoded:
            return None
        userinfo, _, hostport = decoded.rpartition("@")
        if ":" not in userinfo:
            return None
        method, password = userinfo.split(":", 1)
        parsed = _parsed_url(f"ss://x@{hostport}")
    if parsed is None or not method or not password:
        return None
    params = dict(urllib.parse.parse_qsl(query, keep_blank_values=True))
    return ProxyNode(
        type="shadowsocks",
        tag=tag,
        server=parsed.hostname or "",
        port=parsed.port or 0,
        method=method,
        password=password,
        plugin=params.get("plugin", ""),
        plugin_opts=params.get("plugin-opts", "") or params.get("plugin_opts", ""),
    )


def _parse_hysteria2(uri: str) -> Optional[ProxyNode]:
    normalized = "hysteria2://" + uri[len("hy2://") :] if uri.startswith("hy2://") else uri
    parsed = _parsed_url(normalized)
    if parsed is None or not parsed.username:
        return None
    params = _query(parsed)
    node = ProxyNode(
        type="hysteria2",
        tag=_full_unquote(parsed.fragment) or "hy2",
        server=parsed.hostname or "",
        port=parsed.port or 0,
        password=urllib.parse.unquote(parsed.username),
        up_mbps=_bandwidth(params.get("up_mbps", "") or params.get("up", "")),
        down_mbps=_bandwidth(params.get("down_mbps", "") or params.get("down", "")),
    )
    raw_ports = params.get("mport", "") or params.get("ports", "")
    if raw_ports:
        node.server_ports = [part.strip() for part in raw_ports.split(",") if part.strip()]
    obfs_type = params.get("obfs", "")
    obfs_password = params.get("obfs-password", "") or params.get("obfs_password", "")
    if obfs_type in _SUPPORTED_HY2_OBFS:
        node.obfs_type = obfs_type
        node.obfs_password = obfs_password
    elif obfs_password:
        node.obfs_type = "salamander"
        node.obfs_password = obfs_password
    _apply_tls(node, params, default_enabled=True)
    return node


def _parse_tuic(uri: str) -> Optional[ProxyNode]:
    parsed = _parsed_url(uri)
    if parsed is None or not parsed.username:
        return None
    params = _query(parsed)
    node = ProxyNode(
        type="tuic",
        tag=_full_unquote(parsed.fragment) or "tuic",
        server=parsed.hostname or "",
        port=parsed.port or 0,
        uuid=urllib.parse.unquote(parsed.username),
        password=urllib.parse.unquote(parsed.password or params.get("password", "")),
        congestion_control=params.get("congestion_control", "cubic") or "cubic",
    )
    if params.get("network") in {"tcp", "udp"}:
        node.network = params["network"]
    _apply_tls(node, params, default_enabled=True)
    return node


def _parse_anytls(uri: str) -> Optional[ProxyNode]:
    parsed = _parsed_url(uri)
    if parsed is None or not parsed.username:
        return None
    params = _query(parsed)
    node = ProxyNode(
        type="anytls",
        tag=_full_unquote(parsed.fragment) or "anytls",
        server=parsed.hostname or "",
        port=parsed.port or 0,
        password=urllib.parse.unquote(parsed.username),
    )
    _apply_tls(node, params, default_enabled=params.get("security", "tls") != "none")
    return node


def parse_proxy_uri(uri: str) -> Optional[ProxyNode]:
    uri = uri.strip()
    if uri.startswith("vmess://"):
        return _parse_vmess(uri)
    if uri.startswith("vless://"):
        return _parse_vless_or_trojan(uri, "vless")
    if uri.startswith("trojan://"):
        return _parse_vless_or_trojan(uri, "trojan")
    if uri.startswith("ss://"):
        return _parse_shadowsocks(uri)
    if uri.startswith("hysteria2://") or uri.startswith("hy2://"):
        return _parse_hysteria2(uri)
    if uri.startswith("tuic://"):
        return _parse_tuic(uri)
    if uri.startswith("anytls://"):
        return _parse_anytls(uri)
    return None


def _build_tls(node: ProxyNode) -> dict[str, Any]:
    if not node.tls_enabled:
        return {}
    tls: dict[str, Any] = {"enabled": True}
    if node.tls_server_name:
        tls["server_name"] = node.tls_server_name
    if node.tls_insecure:
        tls["insecure"] = True
    if node.tls_alpn:
        tls["alpn"] = node.tls_alpn
    if node.tls_utls_fingerprint:
        tls["utls"] = {"enabled": True, "fingerprint": node.tls_utls_fingerprint}
    if node.tls_reality_public_key:
        reality: dict[str, Any] = {"enabled": True, "public_key": node.tls_reality_public_key}
        if node.tls_reality_short_id:
            reality["short_id"] = node.tls_reality_short_id
        tls["reality"] = reality
    return tls


def _build_transport(node: ProxyNode) -> dict[str, Any]:
    if not node.transport_type:
        return {}
    transport: dict[str, Any] = {"type": node.transport_type}
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


def _current_server_ports(values: list[str]) -> list[str]:
    current = []
    for value in values:
        token = value.strip()
        if re.fullmatch(r"\d+-\d+", token):
            token = token.replace("-", ":", 1)
        if token:
            current.append(token)
    return current


def build_outbound(node: ProxyNode, *, resolver_tag: str = "google") -> dict[str, Any]:
    outbound: dict[str, Any] = {"type": node.type, "tag": node.tag, "server": node.server}
    ports = _current_server_ports(node.server_ports) if node.type == "hysteria2" else []
    if ports:
        outbound["server_ports"] = ports
    else:
        outbound["server_port"] = node.port
    if not _is_ip(node.server):
        outbound["domain_resolver"] = resolver_tag

    if node.type == "vmess":
        outbound.update(
            uuid=node.uuid,
            security=node.security,
            alter_id=node.alter_id,
            global_padding=False,
            authenticated_length=True,
        )
        if node.packet_encoding:
            outbound["packet_encoding"] = node.packet_encoding
    elif node.type == "vless":
        outbound["uuid"] = node.uuid
        if node.flow:
            outbound["flow"] = node.flow
        if node.packet_encoding:
            outbound["packet_encoding"] = node.packet_encoding
    elif node.type == "trojan":
        outbound["password"] = node.password
    elif node.type == "shadowsocks":
        outbound.update(method=node.method, password=node.password)
        if node.plugin:
            outbound["plugin"] = node.plugin
            if node.plugin_opts:
                outbound["plugin_opts"] = node.plugin_opts
    elif node.type == "hysteria2":
        outbound["password"] = node.password
        if node.up_mbps:
            outbound["up_mbps"] = node.up_mbps
        if node.down_mbps:
            outbound["down_mbps"] = node.down_mbps
        if node.obfs_type and node.obfs_password:
            outbound["obfs"] = {"type": node.obfs_type, "password": node.obfs_password}
    elif node.type == "tuic":
        outbound["uuid"] = node.uuid
        if node.password:
            outbound["password"] = node.password
        outbound.update(
            congestion_control=node.congestion_control,
            udp_relay_mode="native",
            zero_rtt_handshake=False,
            heartbeat="10s",
        )
    elif node.type == "anytls":
        outbound.update(password=node.password, idle_session_check_interval="30s", idle_session_timeout="30s")

    if node.network:
        outbound["network"] = node.network
    tls = _build_tls(node)
    if tls:
        outbound["tls"] = tls
    transport = _build_transport(node)
    if transport and node.type in {"vmess", "vless", "trojan"}:
        outbound["transport"] = transport
    return outbound


def _unique_tag(base: str, seen: set[str]) -> str:
    base = base.strip() or "proxy"
    candidate = base
    index = 1
    while candidate in seen:
        candidate = f"{base}-{index}"
        index += 1
    seen.add(candidate)
    return candidate


def build_singbox_config(
    outbounds: list[dict[str, Any]],
    *,
    listen: str = "127.0.0.1",
    mixed_port: int = 2080,
    tun_enabled: bool = False,
) -> dict[str, Any]:
    proxy_tags = [outbound["tag"] for outbound in outbounds]
    selector_targets = (["auto"] if proxy_tags else []) + proxy_tags + ["direct"]
    config: dict[str, Any] = {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [
                {
                    "type": "tls",
                    "tag": "google",
                    "server": "8.8.8.8",
                    "server_port": 853,
                    "tls": {"enabled": True, "server_name": "dns.google"},
                },
                {"type": "local", "tag": "local"},
            ],
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
                "outbounds": selector_targets,
                "default": "auto" if proxy_tags else "direct",
            }
        ]
        + outbounds
        + [{"type": "direct", "tag": "direct"}],
        "route": {
            "rules": [
                {"ip_is_private": True, "action": "route", "outbound": "direct"},
                {"protocol": "dns", "action": "hijack-dns"},
            ],
            "final": "select",
            "auto_detect_interface": True,
            "default_domain_resolver": "google",
        },
    }
    if proxy_tags:
        config["outbounds"].insert(1, {"type": "urltest", "tag": "auto", "outbounds": proxy_tags})
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
    return config


def config_from_uris(
    uris: list[str],
    *,
    listen: str = "127.0.0.1",
    mixed_port: int = 2080,
    tun_enabled: bool = False,
) -> dict[str, Any]:
    outbounds: list[dict[str, Any]] = []
    seen_tags = set(_RESERVED_TAGS)
    for uri in uris:
        uri = uri.strip()
        if not uri or uri.startswith("#"):
            continue
        node = parse_proxy_uri(uri)
        if node is None:
            continue
        node.tag = _unique_tag(node.tag or node.type, seen_tags)
        outbounds.append(build_outbound(node))
    return build_singbox_config(outbounds, listen=listen, mixed_port=mixed_port, tun_enabled=tun_enabled)


def build_singbox_config_bytes(text: str) -> bytes:
    try:
        config = config_from_uris(text.splitlines())
    except AttributeError:
        return b""
    proxy_outbounds = [
        outbound
        for outbound in config.get("outbounds", [])
        if outbound.get("type") not in {"selector", "urltest", "direct"}
    ]
    if not proxy_outbounds:
        return b""
    return json.dumps(config, indent=2, ensure_ascii=False).encode("utf-8")
