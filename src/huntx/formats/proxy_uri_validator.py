from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import re
import uuid
from urllib.parse import parse_qs, unquote, urlsplit

from .common.b64 import b64_decode as _decode_base64_text

_HOST_RE = re.compile(
    r"^(?=.{1,253}\.?$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.?$"
)
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
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
    "wireguard",
    "wg",
    "socks",
    "socks4",
    "socks4a",
    "socks5",
    "anytls",
    "juicity",
    "warp",
    "dns",
    "dnstt",
    "ssh",
    "shadowtls",
    "http",
    "https",
}
_AUTH_REQUIRED_SCHEMES = {
    "trojan",
    "tuic",
    "anytls",
    "wireguard",
    "wg",
}


def _valid_host(host: str | None) -> bool:
    """Validate that a host is public and syntactically acceptable."""
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
    """Validate a TCP or UDP port number."""
    return port is not None and 1 <= port <= 65535


def _validate_port_token(token: str) -> bool:
    """Validate one port or inclusive port-range token."""
    if token.isdigit():
        return _valid_port(int(token))
    match = re.fullmatch(r"(\d+)-(\d+)", token)
    if not match:
        return False
    start, end = map(int, match.groups())
    return 1 <= start <= end <= 65535


def _valid_naive_headers(value: str) -> bool:
    """Validate CRLF-separated NaiveProxy extra headers after URL decoding."""
    if not value:
        return True
    for line in value.splitlines():
        if ":" not in line:
            return False
        name, header_value = line.split(":", 1)
        if not _HEADER_NAME_RE.fullmatch(name.strip()):
            return False
        if "\x00" in header_value:
            return False
    return True


def _validate_ss(uri: str) -> bool:
    """Validate a Shadowsocks share URI."""
    body = uri[5:].split("#", 1)[0]
    if "@" not in body:
        try:
            body = _decode_base64_text(body)
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return False
    if "@" not in body:
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
    """Validate a ShadowsocksR share URI."""
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
    """Validate a VMess share URI and required identity fields."""
    try:
        payload = json.loads(_decode_base64_text(uri[8:].split("#", 1)[0]))
        if not isinstance(payload, dict):
            return False
        uuid.UUID(str(payload.get("id", "")))
        raw_port = payload.get("port")
        if not isinstance(raw_port, (str, int)):
            return False
        port = int(raw_port)
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error, UnicodeDecodeError):
        return False
    return _valid_host(str(payload.get("add", ""))) and _valid_port(port)


def _split_hy2_endpoint(uri: str) -> tuple[str | None, str, list[str]] | None:
    """Validate Hysteria2 host and multi-port authority syntax."""
    try:
        parsed = urlsplit(uri)
    except ValueError:
        return None
    host = parsed.hostname
    if not _valid_host(host):
        return None
    endpoint = parsed.netloc.rsplit("@", 1)[-1]
    port_spec = ""
    if endpoint.startswith("["):
        closing = endpoint.find("]")
        if closing < 0:
            return None
        if len(endpoint) > closing + 1:
            if endpoint[closing + 1] != ":":
                return None
            port_spec = endpoint[closing + 2 :]
    elif ":" in endpoint:
        _, port_spec = endpoint.rsplit(":", 1)
    if not port_spec:
        return host, "443", []
    tokens = [token.strip() for token in port_spec.split(",") if token.strip()]
    if not tokens or not all(_validate_port_token(token) for token in tokens):
        return None
    return host, tokens[0], tokens


def _validate_hysteria2(uri: str) -> bool:
    """Validate a Hysteria2 share URI."""
    endpoint = _split_hy2_endpoint(uri)
    if endpoint is None:
        return False
    try:
        parsed = urlsplit(uri)
    except ValueError:
        return False
    auth = unquote(parsed.username or "")
    if parsed.password is not None:
        auth = f"{auth}:{unquote(parsed.password)}"
    if not auth:
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    obfs_type = query.get("obfs", [""])[0]
    obfs_password = query.get("obfs-password", query.get("obfs_password", [""]))[0]
    if bool(obfs_type) != bool(obfs_password):
        return False
    if obfs_type and obfs_type not in {"salamander", "gecko"}:
        return False
    return True


def _validate_hysteria2_realm(uri: str) -> bool:
    """Validate an official Hysteria2 realm share URI."""
    try:
        parsed = urlsplit(uri)
        port = parsed.port
    except ValueError:
        return False
    if not _valid_host(parsed.hostname):
        return False
    if port is not None and not _valid_port(port):
        return False
    if not unquote(parsed.username or ""):
        return False
    if not parsed.path.lstrip("/"):
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    auth = query.get("auth", [""])[0]
    return bool(auth)


def _validate_hysteria1(uri: str) -> bool:
    """Validate a Hysteria v1 share URI."""
    try:
        parsed = urlsplit(uri)
        port = parsed.port
    except ValueError:
        return False
    if not _valid_host(parsed.hostname) or not _valid_port(port):
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    auth = query.get("auth", [""])[0] or unquote(parsed.username or "")
    if not auth:
        return False
    protocol = query.get("protocol", ["udp"])[0].lower()
    return protocol in {"", "udp", "wechat-video", "faketcp"}


def _validate_mieru(uri: str) -> bool:
    """Validate an opaque standard Mieru base64 share link."""
    payload = uri[len("mieru://") :].split("#", 1)[0]
    if not payload or any(ch.isspace() for ch in payload):
        return False
    try:
        normalized = payload.replace("-", "+").replace("_", "/")
        normalized += "=" * ((4 - len(normalized) % 4) % 4)
        decoded = base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError):
        return False
    return bool(decoded)


def _validate_mierus(uri: str) -> bool:
    """Validate a human-readable Mieru simple share link."""
    try:
        parsed = urlsplit(uri)
    except ValueError:
        return False
    if not _valid_host(parsed.hostname):
        return False
    if not unquote(parsed.username or "") or parsed.password is None or not unquote(parsed.password):
        return False
    if parsed.path not in {"", "/"}:
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    profiles = query.get("profile", [])
    ports = query.get("port", [])
    protocols = query.get("protocol", [])
    if len(profiles) != 1 or not profiles[0]:
        return False
    if not ports or len(ports) != len(protocols):
        return False
    if not all(_validate_port_token(token) for token in ports):
        return False
    return all(protocol.upper() in {"TCP", "UDP"} for protocol in protocols)


def _validate_naive(uri: str) -> bool:
    """Validate a de-facto NaiveProxy ``naive+https`` or ``naive+quic`` URI."""
    try:
        parsed = urlsplit(uri)
        port = parsed.port or 443
    except ValueError:
        return False
    if not _valid_host(parsed.hostname) or not _valid_port(port):
        return False
    if parsed.path not in {"", "/"}:
        return False
    username = unquote(parsed.username or "")
    has_password = parsed.password is not None
    if bool(username) != has_password:
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    headers = query.get("extra-headers", [""])
    return len(headers) == 1 and _valid_naive_headers(headers[0])


def _validate_standard_uri(uri: str) -> bool:
    """Validate endpoint-shaped URI schemes with shared rules."""
    try:
        parsed = urlsplit(uri)
        port = parsed.port
    except ValueError:
        return False
    if not _valid_host(parsed.hostname):
        return False
    scheme = parsed.scheme.lower()
    default_port = 22 if scheme == "ssh" else None
    port = port or default_port
    if not _valid_port(port):
        return False
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
    elif scheme == "juicity":
        try:
            uuid.UUID(username)
        except ValueError:
            return False
        if parsed.password is None or not unquote(parsed.password):
            return False
    elif scheme in _AUTH_REQUIRED_SCHEMES and not username:
        return False
    elif scheme == "shadowtls":
        version = query.get("version", ["3"])[0]
        if version not in {"1", "2", "3"}:
            return False
        password = username or query.get("password", [""])[0]
        if version in {"2", "3"} and not password:
            return False
    elif scheme in {"http", "https"}:
        if not username or parsed.port is None or parsed.path not in {"", "/"}:
            return False
    return True


def validate_proxy_uri(uri: str) -> bool:
    """Return whether a single string is a supported safe proxy URI."""
    if not uri or len(uri) > 16384 or uri != uri.strip() or any(ch in uri for ch in "\r\n\t <>'\""):
        return False
    scheme = uri.split("://", 1)[0].lower() if "://" in uri else ""
    if scheme == "ss":
        return _validate_ss(uri)
    if scheme == "ssr":
        return _validate_ssr(uri)
    if scheme == "vmess":
        return _validate_vmess(uri)
    if scheme in {"hysteria2", "hy2"}:
        return _validate_hysteria2(uri)
    if scheme in {"hysteria2+realm", "hysteria2+realm+http"}:
        return _validate_hysteria2_realm(uri)
    if scheme == "hysteria":
        return _validate_hysteria1(uri)
    if scheme == "mieru":
        return _validate_mieru(uri)
    if scheme == "mierus":
        return _validate_mierus(uri)
    if scheme in {"naive+https", "naive+quic"}:
        return _validate_naive(uri)
    if scheme in {"vless", "trojan", "tuic"} | _GENERIC_ENDPOINT_SCHEMES:
        return _validate_standard_uri(uri)
    return False
