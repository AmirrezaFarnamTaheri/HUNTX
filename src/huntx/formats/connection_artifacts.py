"""Typed extraction of Telegram-shared connection artifacts (not generic proxy nodes).

Parse-only: no Xray/sing-box conversion, network calls or credential logging.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import html
import ipaddress
import json
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

_MAX_MESSAGE_BYTES = 4 * 1024 * 1024
_MAX_RECORDS = 10000
_MAX_PROFILE_BYTES = 65536
_SCHEME_RE = re.compile(r"(?i)(?<![\w])(?P<scheme>soar|cottendns|masterdns|lantern|wireguard|wg)\\?://(?P<body>[^\s<>\"'`]+)")
_HOST_RE = re.compile(r"(?i)^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.ASCII)
_TOR_RE = re.compile(
    r"(?i)\bwebtunnel\s+(?P<host>\[[0-9a-f:.]+\]|[\w.-]+):(?P<port>\d{1,5})\s+"
    r"(?P<fingerprint>[0-9a-f]{40})\s+url=(?:\[(?P<md_url>https?://[^\]\s]+)\]\([^)]+\)|(?P<url>https?://[^\s]+))"
)
_TG_RE = re.compile(r"(?i)https?://(?:t\.me|telegram\.me)/proxy\?[^\s<>\[\]()`\"']+")
_MT_TEXT_RE = re.compile(r"(?im)^Server:\s*`?([a-z0-9.:-]+)`?\s*\nPort:\s*`?(\d{1,5})`?\s*\nSecret:\s*`?([0-9a-f]{32,1024})`?")
_WG_START_RE = re.compile(r"(?i)(?:^|\s)(?:Quote\s+Quote\s+)?\[Interface\]\s*$")
_WG_PEER_RE = re.compile(r"(?i)^\[Peer\]\s*$")
_KEY_VALUE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
_MANUAL_TITLE_RE = re.compile(r"(?i)^\**\s*(Master|Storm|Cotten|Soar(?:\s+2\.2)?)\s*(?:DNS)?\s*:?\s*\**\s*$")
_MANUAL_FIELD_RE = re.compile(r"(?i)^(domain|private\s+key|key)\s*:\s*(.*?)\s*$")
_EXPORT_PREFIX_RE = re.compile(r"^\[\d{1,2}/\d{1,2}/\d{4}[^]]*\]\s+[^:]{1,80}:\s+")
_B64_RE = re.compile(r"^[A-Za-z0-9+/=_-]+$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def may_contain_connection_artifacts(payload: bytes) -> bool:
    """Cheap negative filter for conventional subscriptions."""
    if not payload or b"\0" in payload[:4096]:
        return False
    head = payload[:_MAX_MESSAGE_BYTES].lower()
    return any(token in head for token in (
        b"soar", b"cottendns", b"masterdns", b"lantern", b"wireguard", b"wg://",
        b"[interface]", b"webtunnel", b"t.me/proxy", b"telegram.me/proxy",
        b"domain:",
    ))


def _host_ok(value: str) -> bool:
    if not isinstance(value, str) or len(value) > 253 or not _HOST_RE.fullmatch(value):
        return False
    return value.lower() not in {"localhost", "localhost.localdomain"}


def _endpoint_ok(host: str, port: str) -> bool:
    try:
        return 0 < int(port) <= 65535 and (_host_ok(host) or bool(ipaddress.ip_address(host)))
    except (ValueError, OverflowError):
        return False


def _unwrap(text: str) -> str:
    # Only undo known presentation escapes; never change actual key bytes.
    return (html.unescape(text).replace(r"\://", "://").replace(r"\@", "@")
            .replace(r"\&", "&").replace(r"\<", "<").replace(r"\>", ">"))


def _decode_whitedns(scheme: str, encoded: str) -> dict[str, Any] | None:
    if len(encoded) > _MAX_PROFILE_BYTES * 2 or not _B64_RE.fullmatch(encoded):
        return None
    try:
        value = encoded.replace("-", "+").replace("_", "/")
        data = base64.b64decode(value + "=" * (-len(value) % 4), validate=True)
        if len(data) > _MAX_PROFILE_BYTES:
            return None
        document = json.loads(data)
        if not isinstance(document, dict) or document.get("schema") != "whitedns.profile" or document.get("version") != 1:
            return None
        profile = document.get("profile")
        if not isinstance(profile, dict):
            return None
        server = profile.get("server")
        if not isinstance(server, dict) or not _host_ok(server.get("domain", "")):
            return None
        if scheme == "soar":
            key = server.get("public_key")
            if not isinstance(key, str):
                return None
            if len(base64.b64decode(key, validate=True)) != 32 or not isinstance(profile.get("soarSettings"), dict):
                return None
        else:
            key = server.get("encryption_key")
            method = server.get("encryption_method")
            if profile.get("engine") != scheme or not isinstance(key, str) or len(key) != 64 or not _HEX_RE.fullmatch(key):
                return None
            if type(method) is not int or not 0 <= method <= 255:
                return None
        return document
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError):
        return None


def _decode_share(scheme: str, raw: str) -> dict[str, Any] | None:
    try:
        parsed = urlsplit(raw)
        if scheme in ("wireguard", "wg"):
            host, port = parsed.hostname or "", parsed.port
            if not port or not _endpoint_ok(host, str(port)) or not parsed.username:
                return None
            params = parse_qs(parsed.query, keep_blank_values=True)
            return {"private_key": unquote(parsed.username), "endpoint": f"{host}:{port}",
                    "options": {k: v if len(v) > 1 else v[0] for k, v in params.items()},
                    "name": unquote(parsed.fragment)}
        if scheme == "lantern" and parsed.netloc == "private-server":
            params = parse_qs(parsed.query, keep_blank_values=True)
            lantern_host, lantern_port, token = (
                params.get(k, [""])[0] for k in ("ip", "port", "token")
            )
            if not token or not _endpoint_ok(lantern_host, lantern_port):
                return None
            return {"host": lantern_host, "port": int(lantern_port), "token": token,
                    "exp": params.get("exp", [""])[0],
                    "options": {k: v if len(v) > 1 else v[0] for k, v in params.items()}}
    except (ValueError, TypeError):
        return None
    return None


def _normalize_line(line: str) -> str:
    value = line.strip()
    if value.startswith("[") and re.match(r"^\[\d{1,2}/", value):
        value = _EXPORT_PREFIX_RE.sub("", value)
    if value.lower().startswith("quote quote "):
        value = value[12:]
    if value.endswith("\\"):
        value = value[:-1].strip()
    return value


def _config_blocks(lines: list[str]):
    index = 0
    while index < len(lines):
        if not _WG_START_RE.search(lines[index]):
            index += 1
            continue
        interface: dict[str, str] = {}
        peers: list[dict[str, str]] = []
        selected = interface
        collected = ["[Interface]"]
        index += 1
        while index < len(lines):
            line = lines[index]
            if _WG_START_RE.search(line):
                break
            if _WG_PEER_RE.fullmatch(line):
                selected = {}
                peers.append(selected)
                collected.append("[Peer]")
                index += 1
                continue
            match = _KEY_VALUE_RE.fullmatch(line)
            if match:
                key, value = match.groups()
                selected[key] = value
                # Preserve duplicate fields and their original ordering in
                # the normalized raw block, even when the decoded map cannot.
                collected.append(line)
                index += 1
                continue
            if not line or line.startswith("#"):
                # Comments and blank lines are part of the shared config.
                collected.append(line)
                index += 1
                continue
            break
        # Every peer must have the minimum fields. Never emit a partly parsed
        # multi-peer configuration as if it were safe to use.
        if (interface.get("PrivateKey") and peers
                and all(peer.get("PublicKey") and peer.get("Endpoint") for peer in peers)):
            yield {"protocol": "wireguard", "raw": "\n".join(collected),
                   "decoded": {"interface": interface, "peer": peers[0], "peers": peers},
                   "encoding": "ini"}


def _manual_profiles(lines: list[str]):
    title = None
    fields: dict[str, str] = {}
    mapping = {"master": "masterdns_manual", "storm": "stormdns_manual",
               "cotten": "cottendns_manual", "soar": "soar_manual", "soar 2.2": "soar22_manual"}

    def finish():
        if title and _host_ok(fields.get("domain", "")) and fields.get("key") and 16 <= len(fields["key"]) <= 512:
            raw = f"{title}\ndomain: {fields['domain']}\nkey: {fields['key']}"
            return {"protocol": mapping[title], "raw": raw,
                    "decoded": {"domain": fields["domain"], "key": fields["key"]}, "encoding": "manual"}
        return None

    for original in lines:
        line = original.strip("`")
        head = _MANUAL_TITLE_RE.fullmatch(line)
        if head:
            complete = finish()
            if complete:
                yield complete
            title = re.sub(r"\s+", " ", head.group(1).lower())
            fields = {}
            continue
        if title:
            match = _MANUAL_FIELD_RE.fullmatch(line)
            if match:
                key, value = match.groups()
                fields["domain" if key.lower() == "domain" else "key"] = value.strip("` ")
            elif line and not line.startswith(("#", "\\")):
                complete = finish()
                if complete:
                    yield complete
                title, fields = None, {}
    complete = finish()
    if complete:
        yield complete


def extract_connection_artifacts(text: str) -> list[dict[str, Any]]:
    """Recover validated profile records without implying cross-client support."""
    if len(text.encode("utf-8")) > _MAX_MESSAGE_BYTES:
        raise ValueError("connection artifact message exceeds byte limit")
    if not text:
        return []
    normalized = _unwrap(text)
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append(record: dict[str, Any]) -> None:
        if len(results) >= _MAX_RECORDS:
            raise ValueError("connection artifact count exceeds limit")
        key = hashlib.sha256((record["protocol"] + "\0" + record["raw"]).encode("utf-8")).hexdigest()
        if key not in seen:
            seen.add(key)
            results.append({**record, "client_exportable": False})

    for match in _SCHEME_RE.finditer(normalized):
        scheme = match.group("scheme").lower()
        body = match.group("body").rstrip("\\,;`")
        uri = f"{scheme}://{body}"
        if scheme in ("soar", "cottendns", "masterdns"):
            decoded = _decode_whitedns(scheme, body)
            if decoded is not None:
                append({"protocol": scheme, "raw": uri, "decoded": decoded, "encoding": "whitedns.profile.v1"})
        else:
            decoded = _decode_share(scheme, uri)
            if decoded is not None:
                append({"protocol": "wireguard" if scheme == "wg" else scheme,
                        "raw": uri, "decoded": decoded, "encoding": "share_uri"})

    lines = [_normalize_line(line) for line in normalized.splitlines()]
    for item in _config_blocks(lines):
        append(item)
    for item in _manual_profiles(lines):
        append(item)

    for match in _TOR_RE.finditer(normalized):
        host, port = match.group("host").strip("[]"), match.group("port")
        if not _endpoint_ok(host, port):
            continue
        url = (match.group("md_url") or match.group("url")).rstrip("`),;\\")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            continue
        endpoint = match.group("host") + ":" + port
        fingerprint = match.group("fingerprint").upper()
        append({"protocol": "tor_webtunnel", "raw": f"webtunnel {endpoint} {fingerprint} url={url}",
                "decoded": {"endpoint": endpoint, "fingerprint": fingerprint, "url": url},
                "encoding": "tor_bridge"})

    for match in _TG_RE.finditer(normalized):
        raw = match.group(0).rstrip("),;\\")
        parsed = urlsplit(raw)
        query = parse_qs(parsed.query)
        host, port, secret = (query.get(k, [""])[0] for k in ("server", "port", "secret"))
        if not _endpoint_ok(host, port) or not 16 <= len(secret) <= 1024:
            continue
        clean = f"https://t.me/proxy?server={host}&port={port}&secret={secret}"
        append({"protocol": "mtproto", "raw": clean,
                "decoded": {"host": host, "port": int(port), "secret": secret},
                "encoding": "telegram_mtproto"})
    for match in _MT_TEXT_RE.finditer(normalized):
        host, port, secret = match.groups()
        if not _endpoint_ok(host, port):
            continue
        clean = f"https://t.me/proxy?server={host}&port={port}&secret={secret}"
        append({"protocol": "mtproto", "raw": clean,
                "decoded": {"host": host, "port": int(port), "secret": secret},
                "encoding": "telegram_mtproto"})
    return results


class ConnectionArtifactsHandler:
    """Parse-only typed records; intentionally no subscription builder."""

    parse_only = True

    @property
    def format_id(self) -> str:
        return "connection_artifacts"

    def parse(self, raw_data: bytes, source_info: dict[str, Any]) -> list[dict[str, Any]]:
        if not may_contain_connection_artifacts(raw_data):
            return []
        if len(raw_data) > _MAX_MESSAGE_BYTES:
            raise ValueError("connection artifact message exceeds byte limit")
        try:
            text = raw_data.decode("utf-8")
        except UnicodeDecodeError:
            return []
        return [
            {"unique_hash": hashlib.sha256((item["protocol"] + "\0" + item["raw"]).encode("utf-8")).hexdigest(), "data": item}
            for item in extract_connection_artifacts(text)
        ]

    def build(self, records: list[dict[str, Any]]) -> bytes:
        """Explicitly prohibit accidental publication of extracted secrets."""
        raise NotImplementedError("connection artifacts are parse-only")
