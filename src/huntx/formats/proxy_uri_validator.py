from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import re
import uuid
from urllib.parse import parse_qs, unquote, urlsplit

_HOST_RE = re.compile(
    r"^(?=.{1,253}\.?$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.?$"
)
_SS_METHODS = {
    "aes-128-gcm",
    "aes-192-gcm",
    "aes-256-gcm",
    "chacha20-ietf-poly1305",
    "xchacha20-ietf-poly1305",
    "2022-blake3-aes-128-gcm",
    "2022-blake3-aes-256-gcm",
    "2022-blake3-chacha20-poly1305",
}
_GENERIC_ENDPOINT_SCHEMES = {
    "hysteria",
    "wireguard",
    "wg",
    "socks",
    "socks4",
    "socks5",
    "anytls",
    "juicity",
    "warp",
    "dns",
    "dnstt",
}
_AUTH_REQUIRED_SCHEMES = {
    "trojan",
    "hysteria2",
    "hy2",
    "tuic",
    "hysteria",
    "anytls",
    "juicity",
    "wireguard",
    "wg",
}


def _decode_base64_text(value: str) -> str:
    normalized = value.replace("-", "+").replace("_", "/")
    normalized += "=" * ((4 - len(normalized) % 4) % 4)
    decoded = base64.b64decode(normalized, validate=True)
    return decoded.decode("utf-8")


def _valid_host(host: str | None) -> bool:
    if not host or any(ch.isspace() for ch in host):
        return False
    normalized = host.rstrip(".").lower()
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(normalized)
        return not (
            address.is_unspecified
            or address.is_loopback
            or address.is_multicast
            or address.is_private
            or address.is_link_local
            or address.is_reserved
        )
    except ValueError:
        return bool(_HOST_RE.fullmatch(normalized))


def _valid_port(port: int | None) -> bool:
    return port is not None and 1 <= port <= 65535


def _validate_ss(uri: str) -> bool:
    body = uri[5:].split("#", 1)[0]
    if "@" not in body:
        try:
            body = _decode_base64_text(body)
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return False
    userinfo, endpoint = body.rsplit("@", 1)
    userinfo = unquote(userinfo)
    if ":" not in userinfo:
        try:
            userinfo = _decode_base64_text(userinfo)
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return False
    if ":" not in userinfo:
        return False
    method, password = userinfo.split(":", 1)
    if method not in _SS_METHODS or not password:
        return False
    try:
        parsed = urlsplit(f"ss://placeholder@{endpoint}")
        port = parsed.port
    except ValueError:
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    if "plugin" in query and not query["plugin"][0].strip():
        return False
    return _valid_host(parsed.hostname) and _valid_port(port)


def _validate_ssr(uri: str) -> bool:
    try:
        decoded = _decode_base64_text(uri[6:].split("#", 1)[0])
        main, _, _params = decoded.partition("/?")
        parts = main.split(":")
        if len(parts) < 6:
            return False
        host = ":".join(parts[:-5])
        port = int(parts[-5])
        method = parts[-3]
        password = _decode_base64_text(parts[-1])
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    return _valid_host(host) and _valid_port(port) and bool(method and password)


def _validate_vmess(uri: str) -> bool:
    try:
        payload = json.loads(_decode_base64_text(uri[8:].split("#", 1)[0]))
        if not isinstance(payload, dict):
            return False
        uuid.UUID(str(payload.get("id", "")))
        port = int(payload.get("port"))
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error, UnicodeDecodeError):
        return False
    return _valid_host(str(payload.get("add", ""))) and _valid_port(port)


def _validate_standard_uri(uri: str) -> bool:
    try:
        parsed = urlsplit(uri)
        port = parsed.port
    except ValueError:
        return False
    if not _valid_host(parsed.hostname) or not _valid_port(port):
        return False
    scheme = parsed.scheme.lower()
    query = parse_qs(parsed.query, keep_blank_values=True)
    username = unquote(parsed.username or "")
    if scheme == "vless":
        try:
            uuid.UUID(username)
        except ValueError:
            return False
        security = query.get("security", [""])[0].lower()
        if security == "reality":
            public_key = query.get("pbk", query.get("publicKey", [""]))[0]
            server_name = query.get("sni", [""])[0]
            if not public_key or not server_name:
                return False
    elif scheme in _AUTH_REQUIRED_SCHEMES and not username:
        return False
    if scheme in {"hysteria2", "hy2"}:
        obfs_type = query.get("obfs", [""])[0]
        obfs_password = query.get("obfs-password", query.get("obfs_password", [""]))[0]
        if bool(obfs_type) != bool(obfs_password):
            return False
    return True


def validate_proxy_uri(uri: str) -> bool:
    if (
        not uri
        or len(uri) > 16384
        or uri != uri.strip()
        or any(ch in uri for ch in "\r\n\t <>'\"")
    ):
        return False
    scheme = uri.split("://", 1)[0].lower() if "://" in uri else ""
    if scheme == "ss":
        return _validate_ss(uri)
    if scheme == "ssr":
        return _validate_ssr(uri)
    if scheme == "vmess":
        return _validate_vmess(uri)
    if scheme in {"vless", "trojan", "hysteria2", "hy2", "tuic"} | _GENERIC_ENDPOINT_SCHEMES:
        return _validate_standard_uri(uri)
    return False
