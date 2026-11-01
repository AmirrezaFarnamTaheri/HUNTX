"""Bounded decoding of public proxy feeds into verified standalone share URIs.

Source policies (DNS, routing, chained outbounds) are intentionally not flattened
into misleading single-node links. The normalizer imports compatible nodes only.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any
from urllib.parse import quote, urlencode

import yaml

from ...formats.npvt import NpvtHandler

MAX_FEED_BYTES = 16 * 1024 * 1024
MAX_FEED_NODES = 30_000
# Independently bound YAML tree construction even when the overall feed fits.
MAX_MIHOMO_YAML_BYTES = 8 * 1024 * 1024
_B64 = re.compile(r"^[A-Za-z0-9+/_=-]+$")
_PROXY_TYPES = frozenset({
    "vless", "vmess", "trojan", "ss", "hysteria2", "hy2", "tuic",
})

# Share-link conversion is lossless only for a documented subset of options.
# Unknown Mihomo keys may alter authentication, routing, transport or TLS,
# so reject individual nodes rather than advertising a broken connection.
_MIHOMO_COMMON_FIELDS = frozenset({
    "type", "name", "server", "port", "network", "tls", "servername",
    "sni", "skip-cert-verify", "client-fingerprint", "alpn",
    "reality-opts", "ws-opts", "grpc-opts", "http-opts",
    "h2-opts", "httpupgrade-opts", "udp",
})
_MIHOMO_PROTOCOL_FIELDS = {
    "vless": frozenset({"uuid", "encryption", "flow"}),
    "vmess": frozenset({"uuid", "cipher", "alterId"}),
    "trojan": frozenset({"password"}),
    "ss": frozenset({"cipher", "password"}),
    "hysteria2": frozenset({"password", "ports", "obfs", "obfs-password", "up", "down"}),
    "hy2": frozenset({"password", "ports", "obfs", "obfs-password", "up", "down"}),
    "tuic": frozenset({"uuid", "password"}),
}


class _BoundedMihomoLoader(yaml.SafeLoader):
    """Reject aliases and excessive nesting before constructing untrusted YAML."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            raise ValueError("Mihomo aliases are not accepted in remote feeds")
        depth = getattr(self, "_feed_depth", 0)
        if depth >= 64:
            raise ValueError("Mihomo YAML nesting exceeds limit")
        self._feed_depth = depth + 1
        try:
            return super().compose_node(parent, index)
        finally:
            self._feed_depth = depth


def _scalar(value: Any) -> str:
    return str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ""


def _endpoint(node: dict[str, Any]) -> str | None:
    host = _scalar(node.get("server"))
    port = node.get("port")
    if not host or any(char in host for char in "@/?# \t\r\n"):
        return None
    if isinstance(port, bool) or not isinstance(port, (str, int)):
        return None
    try:
        number = int(port)
    except (TypeError, ValueError):
        return None
    if not 1 <= number <= 65535 or str(port) not in {str(number), f"{number}.0"}:
        return None
    # Host validation is performed again by HUNTX's canonical URI validator.
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{number}"


def _mihomo_uri(node: dict[str, Any]) -> str | None:
    """Convert only Mihomo parameters that the standard share URIs represent."""
    kind = _scalar(node.get("type")).lower()
    if kind not in _PROXY_TYPES:
        return None
    allowed = _MIHOMO_COMMON_FIELDS | _MIHOMO_PROTOCOL_FIELDS[kind]
    if set(node) - allowed or node.get("udp") is False:
        return None
    # Trojan and QUIC protocols require TLS; explicit opt-outs are not portable.
    if kind in {"trojan", "hysteria2", "hy2", "tuic"} and node.get("tls") is False:
        return None
    if node.get("flow") and kind == "vless" and node.get("network", "tcp") not in ("tcp", "raw"):
        return None
    endpoint = _endpoint(node)
    if not endpoint or any(k in node for k in (
        "dialer-proxy", "smux", "plugin", "ech-opts", "certificate",
        "private-key", "xhttp-opts", "kcp-opts", "shadow-tls",
        "interface-name", "routing-mark", "mptcp", "tfo", "uot",
        "udp-over-tcp", "packet-encoding", "obfs-plugin", "obfs-opts",
    )):
        return None

    network = _scalar(node.get("network") or "tcp").lower()
    if network == "raw":
        network = "tcp"
    if network not in {"tcp", "ws", "grpc", "h2", "http", "httpupgrade"}:
        return None

    name = _scalar(node.get("name"))[:160]
    remark = "#" + quote(name, safe="") if name else ""
    q: dict[str, str] = {}
    if network not in {"tcp"}:
        q["type"] = "http" if network in {"h2", "http"} else network
        options_key = {
            "ws": "ws-opts",
            "grpc": "grpc-opts",
            "http": "http-opts",
            "h2": "h2-opts",
            "httpupgrade": "httpupgrade-opts",
        }.get(network, "")
        options = node.get(options_key) or {}
        if not isinstance(options, dict):
            return None
        if network == "ws":
            if set(options) - {"path", "headers"}:
                return None
            if any(k in options for k in ("max-early-data", "early-data-header-name")):
                return None
            headers = options.get("headers") or {}
            if not isinstance(headers, dict):
                return None
            # Arbitrary headers cannot be represented by canonical URI options.
            if set(k.lower() for k in headers) - {"host"}:
                return None
            host = headers.get("Host") or headers.get("host")
            if isinstance(host, list):
                host = host[0] if len(host) == 1 else None
            if host:
                q["host"] = _scalar(host)
            if options.get("path"):
                q["path"] = _scalar(options["path"])
        elif network == "grpc":
            if set(options) - {"grpc-service-name"}:
                return None
            if options.get("grpc-service-name"):
                q["serviceName"] = _scalar(options["grpc-service-name"])
        else:
            # Multiple paths, methods and arbitrary headers are policy-dependent.
            if set(options) - {"method", "path", "host"}:
                return None
            if options.get("method") not in (None, "GET"):
                return None
            paths = options.get("path") or []
            if isinstance(paths, list):
                if len(paths) > 1:
                    return None
                paths = paths[0] if paths else ""
            if paths:
                q["path"] = _scalar(paths)
            hosts = options.get("host") or []
            if isinstance(hosts, list):
                if len(hosts) > 1:
                    return None
                hosts = hosts[0] if hosts else ""
            if hosts:
                q["host"] = _scalar(hosts)

    sni = _scalar(node.get("servername") or node.get("sni"))
    reality = node.get("reality-opts") or {}
    if not isinstance(reality, dict):
        return None
    if reality:
        public_key = _scalar(reality.get("public-key"))
        if not public_key or set(reality) - {"public-key", "short-id"}:
            return None
        q["security"] = "reality"
        q["pbk"] = public_key
        if reality.get("short-id"):
            q["sid"] = _scalar(reality["short-id"])
    elif node.get("tls"):
        q["security"] = "tls"
    if sni:
        q["sni"] = sni
    if node.get("skip-cert-verify"):
        q["insecure"] = "1"
    fingerprint = _scalar(node.get("client-fingerprint"))
    if fingerprint:
        q["fp"] = fingerprint
    alpn = node.get("alpn")
    if isinstance(alpn, list) and alpn:
        q["alpn"] = ",".join(_scalar(v) for v in alpn)
    elif alpn not in (None, []):
        return None

    if kind == "ss":
        if network != "tcp" or q or sni or node.get("skip-cert-verify"):
            return None
        method = _scalar(node.get("cipher"))
        password = _scalar(node.get("password"))
        if not method or not password or reality or node.get("tls"):
            return None
        auth = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode().rstrip("=")
        return f"ss://{auth}@{endpoint}{remark}"

    if kind == "vmess":
        uuid = _scalar(node.get("uuid"))
        if not uuid or reality:
            return None
        profile = {
            "v": "2", "ps": name, "add": _scalar(node.get("server")),
            "port": str(node["port"]), "id": uuid,
            "aid": _scalar(node.get("alterId") or 0),
            "scy": _scalar(node.get("cipher") or "auto"),
            "net": q.get("type", "tcp"), "type": "none",
            "host": q.get("host", ""), "path": q.get("path", ""),
            "tls": "tls" if node.get("tls") else "",
            "sni": sni, "alpn": q.get("alpn", ""),
        }
        body = base64.urlsafe_b64encode(
            json.dumps(profile, separators=(",", ":"), ensure_ascii=False).encode()
        ).decode().rstrip("=")
        return "vmess://" + body

    if kind in {"vless", "trojan", "hysteria2", "hy2", "tuic"}:
        if kind == "vless":
            auth = _scalar(node.get("uuid"))
            q["encryption"] = _scalar(node.get("encryption") or "none")
            if node.get("flow"):
                q["flow"] = _scalar(node["flow"])
        elif kind == "trojan":
            auth = _scalar(node.get("password"))
        elif kind in {"hysteria2", "hy2"}:
            auth = _scalar(node.get("password"))
            if node.get("ports"):
                q["mport"] = _scalar(node["ports"])
            if node.get("obfs"):
                q["obfs"] = _scalar(node["obfs"])
                q["obfs-password"] = _scalar(node.get("obfs-password"))
            if node.get("up") or node.get("down"):
                # Bandwidth shapers are not identical across clients.
                return None
        else:
            uuid = _scalar(node.get("uuid"))
            password = _scalar(node.get("password"))
            auth = f"{uuid}:{password}" if uuid and password else ""
        if not auth:
            return None
        protocol = "hysteria2" if kind == "hy2" else kind
        query = "?" + urlencode(q) if q else ""
        return f"{protocol}://{quote(auth, safe=':')}@{endpoint}{query}{remark}"
    return None


def _extract_checked(text: str) -> list[str]:
    handler = NpvtHandler()
    records = handler.parse(text.encode("utf-8"), {"filename": "remote.txt"})
    links = list(dict.fromkeys(
        rec["data"]["line"] for rec in records
        if isinstance(rec.get("data", {}).get("line"), str)
    ))
    if len(links) > MAX_FEED_NODES:
        raise ValueError("remote feed exceeds bounded node count")
    return links


def _audit_profiles(value: Any) -> dict[str, int | str]:
    profiles = value if isinstance(value, list) else [value]
    if not profiles or any(
        not isinstance(p, dict) or not isinstance(p.get("outbounds"), list)
        for p in profiles
    ):
        raise ValueError("expected full Xray profiles with outbounds")
    endpoints = 0
    policy_bound = 0
    for profile in profiles:
        for item in profile["outbounds"]:
            if not isinstance(item, dict) or item.get("protocol") not in {
                "vmess", "vless", "trojan", "shadowsocks", "socks", "http"
            }:
                continue
            endpoints += 1
            if (item.get("streamSettings") or {}).get("sockopt", {}).get("dialerProxy"):
                policy_bound += 1
    if len(profiles) > MAX_FEED_NODES:
        raise ValueError("remote profile bundle exceeds inspection limit")
    return {
        "kind": "xray_profile_audit", "profiles": len(profiles),
        "candidate_endpoints": endpoints, "policy_bound_endpoints": policy_bound,
        "nodes": 0,
    }


def normalize_feed(payload: bytes, mode: str = "auto") -> tuple[bytes, dict[str, int | str]]:
    """Decode once and validate ALL emitted URIs before entering the state DB."""
    if not payload or len(payload) > MAX_FEED_BYTES:
        raise ValueError("empty or oversized HTTP feed")
    try:
        text = payload.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("feed content must be UTF-8") from exc
    if not text or re.match(r"(?is)^<!doctype html|^<html\b", text):
        raise ValueError("HTTP feed contains no proxy data")

    if mode == "xray_profile_audit":
        try:
            profile_value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Xray profile source did not return JSON") from exc
        return b"", _audit_profiles(profile_value)
    if mode != "auto":
        raise ValueError("unsupported HTTP feed inspection mode")

    kind = "uri_text"
    skipped = 0
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("malformed JSON feed") from exc
        if isinstance(data, list) and len(data) > MAX_FEED_NODES:
            raise ValueError("JSON feed exceeds node limit")
        if isinstance(data, list) and all(isinstance(x, str) for x in data):
            text = "\n".join(data)
            kind = "json_links"
        elif isinstance(data, dict) and isinstance(data.get("proxies"), list):
            if len(data["proxies"]) > MAX_FEED_NODES:
                raise ValueError("Mihomo JSON feed exceeds node limit")
            kind = "mihomo"
            converted = [_mihomo_uri(x) if isinstance(x, dict) else None for x in data["proxies"]]
            skipped = converted.count(None)
            text = "\n".join(x for x in converted if x is not None)
        else:
            raise ValueError("full JSON profiles are not independent share-link feeds")
    elif text.startswith("proxies:") or text.startswith("---\nproxies:"):
        if len(payload) > MAX_MIHOMO_YAML_BYTES:
            raise ValueError("Mihomo YAML exceeds conservative size limit")
        try:
            data = yaml.load(text, Loader=_BoundedMihomoLoader)
        except (yaml.YAMLError, RecursionError) as exc:
            raise ValueError("invalid or deeply nested Mihomo YAML") from exc
        if not isinstance(data, dict) or not isinstance(data.get("proxies"), list):
            raise ValueError("Mihomo feed lacks a proxies array")
        if len(data["proxies"]) > MAX_FEED_NODES:
            raise ValueError("Mihomo feed exceeds bounded node count")
        kind = "mihomo"
        converted = [_mihomo_uri(x) if isinstance(x, dict) else None for x in data["proxies"]]
        skipped = converted.count(None)
        text = "\n".join(x for x in converted if x is not None)
    elif "://" not in text and len(text) >= 16:
        compact = "".join(text.split())
        if not _B64.fullmatch(compact):
            raise ValueError("feed is neither share links nor valid base64")
        if len(compact) % 4 == 1:
            raise ValueError("malformed base64 feed")
        try:
            decoded = base64.b64decode(
                compact + "=" * (-len(compact) % 4), altchars=b"-_", validate=True
            )
            text = decoded.decode("utf-8-sig")
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise ValueError("malformed base64 feed") from exc
        kind = "base64_links"

    links = _extract_checked(text)
    if not links:
        raise ValueError("HTTP feed contains no valid independent share links")
    if len(links) > MAX_FEED_NODES:
        raise ValueError("HTTP feed exceeds bounded node count")
    return ("\n".join(links) + "\n").encode("utf-8"), {
        "kind": kind, "nodes": len(links), "skipped_incompatible": skipped,
    }
