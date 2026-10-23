"""Connection identity, independent of presentation and share-link spelling.

Use the client parser for typed fields and defaults, but retain unmodeled
options. Dropping unknown options would silently merge distinct connections.
"""
from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .singbox import build_outbound, parse_proxy_uri
from .vmess import decode_vmess_payload

_COMMON = {'sni', 'peer', 'host', 'insecure', 'allowInsecure', 'fp', 'alpn', 'pbk', 'sid'}
_TRANSPORT = {'path', 'serviceName', 'service_name'}
_TYPED = {
    'vless': _COMMON | _TRANSPORT | {'flow', 'packetEncoding', 'packet_encoding'},
    'trojan': _COMMON | _TRANSPORT,
    'ss': {'plugin', 'plugin-opts', 'plugin_opts'},
}
_VMESS = {'v', 'ps', 'add', 'port', 'id', 'aid', 'scy', 'net', 'type', 'tls',
          'host', 'sni', 'allowInsecure', 'alpn', 'path', 'serviceName', 'packetEncoding'}
_TRANSPORTS = {'', 'tcp', 'raw', 'ws', 'grpc', 'h2', 'http', 'httpupgrade', 'quic'}


def client_identity(uri: str) -> str | None:
    """Return a typed, loss-aware connection key, or defer opaque protocols."""
    parsed = urlsplit(uri)
    scheme = parsed.scheme.lower()
    if scheme not in {'vmess', 'vless', 'trojan', 'ss'}:
        return None
    # Scheme enum values are case-insensitive in share-link ecosystems. Feed
    # normalized values to the typed parser while retaining original values
    # below for unknown-option identity.
    query = parse_qsl(parsed.query, keep_blank_values=True)
    normalized_query = [(key, value.lower() if key.lower() in {'security', 'type', 'network'} else value)
                        for key, value in query]
    parser_uri = urlunsplit(parsed._replace(query=urlencode(normalized_query)))
    node = parse_proxy_uri(parser_uri)
    if node is None:
        return None
    node.server = node.server.lower()
    try:
        node.uuid = str(uuid.UUID(node.uuid))
    except (ValueError, AttributeError):
        # Some clients accept short custom IDs as case-sensitive strings.
        pass
    node.tls_server_name = node.tls_server_name.lower()
    # Compare effective connection fields, not dormant model properties (for
    # example an SNI value with TLS disabled). Preserve unknown URI extensions
    # separately below instead of trusting a lossy conversion as the whole key.
    values = build_outbound(node)
    values.pop('tag', None)
    extras: dict[str, Any] = {}
    if scheme == 'vmess':
        payload = decode_vmess_payload(uri)
        if payload is None:
            return None
        extras = {key: value for key, value in payload.items() if key not in _VMESS}
        # Unknown transport/header/security extensions are connection settings.
        options: list[tuple[str, set[Any]]] = [
            ('net', _TRANSPORTS), ('type', {'', 'none'}),
            ('tls', {'', 'tls'}), ('v', {'', '2', 2}),
        ]
        for key, accepted in options:
            value = payload.get(key, '')
            if not isinstance(value, (str, int)) or value not in accepted:
                extras[key] = value
    else:
        params = parse_qsl(parsed.query, keep_blank_values=True)
        for key, value in params:
            # Preserve repeats even for a recognized key: client precedence can
            # differ, so only a single-valued option can be normalized away.
            repeated = sum(k == key for k, _ in params) > 1
            modeled = key in _TYPED[scheme]
            if key in {'insecure', 'allowInsecure'} and value.strip().lower() not in {
                '', '0', '1', 'true', 'false', 'yes', 'no'
            }:
                modeled = False
            if key == 'type' and value.lower() in _TRANSPORTS:
                modeled = True
            if key == 'security' and value.lower() in {'', 'none', 'tls', 'reality'}:
                modeled = True
            if key == 'headerType' and value in {'', 'none'}:
                modeled = True
            if key == 'encryption' and scheme == 'vless' and value in {'', 'none'}:
                modeled = True
            if not modeled or repeated:
                extras.setdefault(key, []).append(value)
        # An ordinary trailing slash is URL syntax, other URI paths remain data.
        if parsed.path not in {'', '/'}:
            extras['_uri_path'] = parsed.path
        if scheme != 'ss' and parsed.password is not None:
            extras['_uri_password'] = parsed.password
    return json.dumps([values, extras], sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'))
