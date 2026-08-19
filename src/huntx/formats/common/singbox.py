"""Render supported proxy share URIs as a sing-box 1.14+ client configuration.

The parser intentionally distinguishes between:
- URI forms that can be represented faithfully as current sing-box outbounds;
- legacy/opaque schemes that HUNTX can preserve elsewhere but should not convert
  into invalid sing-box JSON.

WireGuard links remain excluded here because sing-box removed the legacy
WireGuard outbound in 1.13; WireGuard is now represented as an endpoint and
requires key/address fields that generic endpoint URIs do not provide.
"""
from __future__ import annotations
import ipaddress
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Optional
from .b64 import b64_decode
TARGET_SINGBOX_VERSION = '1.14+'
_RESERVED_TAGS = {'select', 'auto', 'direct'}
_SUPPORTED_HY2_OBFS = {'salamander', 'gecko'}


@dataclass
class ProxyNode:
    type: str
    tag: str
    server: str = ''
    port: int = 0
    uuid: str = ''
    username: str = ''
    password: str = ''
    method: str = ''
    version: str = ''
    alter_id: int = 0
    security: str = 'auto'
    flow: str = ''
    network: str = ''
    packet_encoding: str = ''
    plugin: str = ''
    plugin_opts: str = ''
    tls_enabled: bool = False
    tls_server_name: str = ''
    tls_insecure: bool = False
    tls_alpn: list[str] = field(default_factory=list)
    tls_utls_fingerprint: str = ''
    tls_reality_public_key: str = ''
    tls_reality_short_id: str = ''
    transport_type: str = ''
    transport_path: str = ''
    transport_host: list[str] = field(default_factory=list)
    transport_service_name: str = ''
    obfs_type: str = ''
    obfs_password: str = ''
    congestion_control: str = 'cubic'
    up_mbps: int = 0
    down_mbps: int = 0
    server_ports: list[str] = field(default_factory=list)
    realm_server_url: str = ''
    realm_token: str = ''
    realm_id: str = ''
    realm_stun_servers: list[str] = field(default_factory=list)
    naive_quic: bool = False

    @property
    def tls_reality_enabled(self) -> bool:
        """Return whether REALITY is configured for this node."""
        return bool(self.tls_reality_public_key)


def _safe_b64(value: str) -> str:
    """Decode base64 text and return an empty string on invalid input."""
    try:
        return b64_decode(value)
    except Exception:
        return ''


def _full_unquote(value: str) -> str:
    """Repeatedly percent-decode a value until it becomes stable."""
    previous = None
    while '%' in value and value != previous:
        previous = value
        value = urllib.parse.unquote(value)
    return value


def _parse_int(value: Any, default: int = 0) -> int:
    """Parse an integer value with a caller-provided fallback."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parsed_url(uri: str, *, default_port: int = 0) -> Optional[tuple[urllib.parse.SplitResult, int]]:
    """Parse an endpoint URI and validate its host and effective port."""
    try:
        parsed = urllib.parse.urlsplit(uri)
        if not parsed.hostname:
            return None
        try:
            port = parsed.port
        except ValueError:
            return None
        port = port or default_port
        if not 1 <= port <= 65535:
            return None
        return parsed, port
    except ValueError:
        return None


def _query(parsed: urllib.parse.SplitResult) -> dict[str, str]:
    """Return single-value query parameters from a parsed URI."""
    return dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))


def _query_multi(parsed: urllib.parse.SplitResult) -> dict[str, list[str]]:
    """Return multi-value query parameters from a parsed URI."""
    values: dict[str, list[str]] = {}
    for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        values.setdefault(key, []).append(value)
    return values


def _is_ip(value: str) -> bool:
    """Return whether a string is an IPv4 or IPv6 literal."""
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _bandwidth(value: str) -> int:
    """Extract an integer bandwidth value from free-form text."""
    match = re.search('\\d+', value or '')
    return int(match.group(0)) if match else 0


def _apply_tls(node: ProxyNode, params: dict[str, str], *, default_enabled: bool = False) -> None:
    """Populate TLS-related fields on a proxy node from URI parameters."""
    security = params.get('security', '')
    node.tls_enabled = default_enabled or security in {'tls', 'reality'}
    node.tls_server_name = params.get('sni', '') or params.get('peer', '') or params.get('host', '')
    node.tls_insecure = params.get('insecure', '0') == '1' or params.get('allowInsecure', '0') == '1'
    node.tls_utls_fingerprint = params.get('fp', '')
    if params.get('alpn'):
        node.tls_alpn = [part.strip() for part in params['alpn'].split(',') if part.strip()]
    if security == 'reality' or params.get('pbk'):
        node.tls_enabled = True
        node.tls_reality_public_key = params.get('pbk', '')
        node.tls_reality_short_id = params.get('sid', '')


def _apply_transport(node: ProxyNode, params: dict[str, str], transport: str) -> None:
    """Populate transport fields on a proxy node from URI parameters."""
    if transport == 'ws':
        node.transport_type = 'ws'
        node.transport_path = params.get('path', '')
        if params.get('host'):
            node.transport_host = [params['host']]
    elif transport == 'grpc':
        node.transport_type = 'grpc'
        node.transport_service_name = params.get('serviceName', '') or params.get('service_name', '') or 'grpc'
    elif transport in {'h2', 'http'}:
        node.transport_type = 'http'
        node.transport_path = params.get('path', '')
        if params.get('host'):
            node.transport_host = [part.strip() for part in params['host'].split(',') if part.strip()]
    elif transport == 'httpupgrade':
        node.transport_type = 'httpupgrade'
        node.transport_path = params.get('path', '')
        if params.get('host'):
            node.transport_host = [params['host']]
    elif transport == 'quic':
        node.transport_type = 'quic'


def _parse_vmess(uri: str) -> Optional[ProxyNode]:
    """Parse a VMess share URI into a proxy node."""
    decoded = _safe_b64(uri[len('vmess://'):])
    if not decoded:
        return None
    try:
        data = json.loads(decoded)
    except (TypeError, ValueError):
        return None
    server = str(data.get('add', '')).strip()
    port = _parse_int(data.get('port'))
    uuid = str(data.get('id', '')).strip()
    if not server or not uuid or not 1 <= port <= 65535:
        return None
    node = ProxyNode(
        type='vmess',
        tag=str(data.get('ps', '') or server),
        server=server,
        port=port,
        uuid=uuid,
        alter_id=max(0, _parse_int(data.get('aid'))),
        security=str(data.get('scy', 'auto') or 'auto'),
        packet_encoding=str(data.get('packetEncoding', '') or ''),
        tls_enabled=data.get('tls', '') == 'tls',
        tls_server_name=str(data.get('sni', '') or data.get('host', '') or ''),
        tls_insecure=str(data.get('allowInsecure', '0')) == '1',
    )
    if data.get('alpn'):
        node.tls_alpn = [part.strip() for part in str(data['alpn']).split(',') if part.strip()]
    _apply_transport(
        node,
        {
            'path': str(data.get('path', '') or ''),
            'host': str(data.get('host', '') or ''),
            'serviceName': str(data.get('serviceName', '') or data.get('path', '') or ''),
        },
        str(data.get('net', 'tcp') or 'tcp').lower(),
    )
    return node


def _parse_vless_or_trojan(uri: str, node_type: str) -> Optional[ProxyNode]:
    """Parse a VLESS or Trojan share URI into a proxy node."""
    result = _parsed_url(uri)
    if result is None:
        return None
    parsed, port = result
    if not parsed.username:
        return None
    params = _query(parsed)
    credential = urllib.parse.unquote(parsed.username)
    node = ProxyNode(
        type=node_type,
        tag=_full_unquote(parsed.fragment) or node_type,
        server=parsed.hostname or '',
        port=port,
        uuid=credential if node_type == 'vless' else '',
        password=credential if node_type == 'trojan' else '',
        flow=params.get('flow', '') if node_type == 'vless' else '',
        packet_encoding=(params.get('packetEncoding', '') or params.get('packet_encoding', '') or 'xudp')
        if node_type == 'vless'
        else '',
    )
    if params.get('network') in {'tcp', 'udp'}:
        node.network = params['network']
    _apply_tls(node, params, default_enabled=node_type == 'trojan' and params.get('security', 'tls') != 'none')
    _apply_transport(node, params, params.get('type', 'tcp').lower())
    return node


def _parse_shadowsocks_json(data: dict[str, Any], tag: str) -> Optional[ProxyNode]:
    """Parse a Shadowsocks JSON payload into a proxy node."""
    server = str(data.get('server', '')).strip()
    port = _parse_int(data.get('server_port'))
    method = str(data.get('method', '')).strip()
    password = str(data.get('password', ''))
    if not server or not method or not password or not 1 <= port <= 65535:
        return None
    return ProxyNode(
        type='shadowsocks',
        tag=tag or 'ss',
        server=server,
        port=port,
        method=method,
        password=password,
        plugin=str(data.get('plugin', '') or ''),
        plugin_opts=str(data.get('plugin_opts', '') or ''),
    )


def _parse_shadowsocks(uri: str) -> Optional[ProxyNode]:
    """Parse a SIP002-compatible Shadowsocks URI into a proxy node."""
    raw = uri[len('ss://'):]
    main, _, fragment = raw.partition('#')
    tag = _full_unquote(fragment) or 'ss'
    if '@' in main:
        userinfo, _, hostinfo = main.partition('@')
        decoded = urllib.parse.unquote(userinfo)
        decoded = _safe_b64(decoded) or decoded
        if ':' not in decoded:
            return None
        method, password = decoded.split(':', 1)
        hostport, _, query = hostinfo.partition('?')
        parsed_result = _parsed_url(f'ss://x@{hostport}')
    else:
        encoded, _, query = main.partition('?')
        decoded = _safe_b64(urllib.parse.unquote(encoded))
        if not decoded:
            return None
        if decoded.lstrip().startswith('{'):
            try:
                return _parse_shadowsocks_json(json.loads(decoded), tag)
            except (TypeError, ValueError):
                return None
        if '@' not in decoded:
            return None
        userinfo, _, hostport = decoded.rpartition('@')
        if ':' not in userinfo:
            return None
        method, password = userinfo.split(':', 1)
        parsed_result = _parsed_url(f'ss://x@{hostport}')
    if parsed_result is None or not method or not password:
        return None
    parsed, port = parsed_result
    params = dict(urllib.parse.parse_qsl(query, keep_blank_values=True))
    return ProxyNode(
        type='shadowsocks',
        tag=tag,
        server=parsed.hostname or '',
        port=port,
        method=method,
        password=password,
        plugin=params.get('plugin', ''),
        plugin_opts=params.get('plugin-opts', '') or params.get('plugin_opts', ''),
    )


def _split_hy2_authority(uri: str) -> Optional[tuple[urllib.parse.SplitResult, str, int, list[str]]]:
    """Parse Hysteria2 host and multi-port authority syntax."""
    try:
        parsed = urllib.parse.urlsplit(uri)
    except ValueError:
        return None
    if not parsed.hostname:
        return None
    endpoint = parsed.netloc.rsplit('@', 1)[-1]
    port_spec = ''
    if endpoint.startswith('['):
        closing = endpoint.find(']')
        if closing < 0:
            return None
        if len(endpoint) > closing + 1:
            if endpoint[closing + 1] != ':':
                return None
            port_spec = endpoint[closing + 2:]
    elif ':' in endpoint:
        _, port_spec = endpoint.rsplit(':', 1)
    if not port_spec:
        return parsed, parsed.hostname, 443, []
    tokens = [token.strip() for token in port_spec.split(',') if token.strip()]
    if not tokens:
        return None
    normalized: list[str] = []
    first_port = 0
    for token in tokens:
        if re.fullmatch('\\d+', token):
            value = int(token)
            if not 1 <= value <= 65535:
                return None
            first_port = first_port or value
            normalized.append(token)
            continue
        match = re.fullmatch('(\\d+)-(\\d+)', token)
        if not match:
            return None
        start, end = map(int, match.groups())
        if not 1 <= start <= end <= 65535:
            return None
        first_port = first_port or start
        normalized.append(token)
    return parsed, parsed.hostname, first_port, normalized if len(normalized) > 1 or '-' in normalized[0] else []


def _parse_hysteria2(uri: str) -> Optional[ProxyNode]:
    """Parse a Hysteria2 share URI into a proxy node."""
    normalized = 'hysteria2://' + uri[len('hy2://'):] if uri.startswith('hy2://') else uri
    endpoint = _split_hy2_authority(normalized)
    if endpoint is None:
        return None
    parsed, server, port, server_ports = endpoint
    if not parsed.username:
        return None
    params = _query(parsed)
    auth = urllib.parse.unquote(parsed.username)
    if parsed.password is not None:
        auth = f'{auth}:{urllib.parse.unquote(parsed.password)}'
    node = ProxyNode(
        type='hysteria2',
        tag=_full_unquote(parsed.fragment) or 'hy2',
        server=server,
        port=port,
        password=auth,
        server_ports=server_ports,
    )
    raw_ports = params.get('mport', '') or params.get('ports', '')
    if raw_ports and not server_ports:
        node.server_ports = [part.strip() for part in raw_ports.split(',') if part.strip()]
    obfs_type = params.get('obfs', '')
    obfs_password = params.get('obfs-password', '') or params.get('obfs_password', '')
    if obfs_type in _SUPPORTED_HY2_OBFS:
        node.obfs_type = obfs_type
        node.obfs_password = obfs_password
    elif obfs_password:
        node.obfs_type = 'salamander'
        node.obfs_password = obfs_password
    _apply_tls(node, params, default_enabled=True)
    return node


def _parse_hysteria2_realm(uri: str) -> Optional[ProxyNode]:
    """Parse a Hysteria2 Realm URI only when sing-box-required fields exist."""
    try:
        parsed = urllib.parse.urlsplit(uri)
    except ValueError:
        return None
    if not parsed.hostname or not parsed.username:
        return None
    realm_id = urllib.parse.unquote(parsed.path.lstrip('/')).strip()
    if not realm_id:
        return None
    params_multi = _query_multi(parsed)
    auth_values = params_multi.get('auth', [])
    stun_values = [value for value in params_multi.get('stun', []) if value]
    if not auth_values or not auth_values[0] or not stun_values:
        return None
    scheme = parsed.scheme.lower()
    transport_scheme = 'http' if scheme.endswith('+http') else 'https'
    host = parsed.hostname
    try:
        parsed_port = parsed.port
    except ValueError:
        return None
    if parsed_port:
        host = f'{host}:{parsed_port}'
    realm_url = f'{transport_scheme}://{host}'
    node = ProxyNode(
        type='hysteria2',
        tag=_full_unquote(parsed.fragment) or 'hy2-realm',
        password=auth_values[0],
        realm_server_url=realm_url,
        realm_token=urllib.parse.unquote(parsed.username),
        realm_id=realm_id,
        realm_stun_servers=stun_values,
    )
    params = {key: values[0] for key, values in params_multi.items() if values}
    _apply_tls(node, params, default_enabled=True)
    return node


def _parse_hysteria1(uri: str) -> Optional[ProxyNode]:
    """Parse an official Hysteria v1 share URI."""
    result = _parsed_url(uri)
    if result is None:
        return None
    parsed, port = result
    params = _query(parsed)
    protocol = params.get('protocol', 'udp').lower()
    if protocol not in {'', 'udp'}:
        return None
    auth = params.get('auth', '') or urllib.parse.unquote(parsed.username or '')
    up_mbps = _bandwidth(params.get('upmbps', '') or params.get('up_mbps', ''))
    down_mbps = _bandwidth(params.get('downmbps', '') or params.get('down_mbps', ''))
    if not auth or not up_mbps or not down_mbps:
        return None
    node = ProxyNode(
        type='hysteria',
        tag=_full_unquote(parsed.fragment) or 'hysteria',
        server=parsed.hostname or '',
        port=port,
        password=auth,
        up_mbps=up_mbps,
        down_mbps=down_mbps,
    )
    if params.get('obfs', '').lower() == 'xplus':
        node.obfs_password = params.get('obfsParam', '') or params.get('obfs_param', '')
    _apply_tls(node, params, default_enabled=True)
    return node


def _parse_tuic(uri: str) -> Optional[ProxyNode]:
    """Parse a TUIC share URI into a proxy node."""
    result = _parsed_url(uri, default_port=443)
    if result is None:
        return None
    parsed, port = result
    if not parsed.username:
        return None
    params = _query(parsed)
    node = ProxyNode(
        type='tuic',
        tag=_full_unquote(parsed.fragment) or 'tuic',
        server=parsed.hostname or '',
        port=port,
        uuid=urllib.parse.unquote(parsed.username),
        password=urllib.parse.unquote(parsed.password or params.get('password', '')),
        congestion_control=params.get('congestion_control', 'cubic') or 'cubic',
    )
    if params.get('network') in {'tcp', 'udp'}:
        node.network = params['network']
    _apply_tls(node, params, default_enabled=True)
    return node


def _parse_anytls(uri: str) -> Optional[ProxyNode]:
    """Parse an AnyTLS share URI into a proxy node."""
    result = _parsed_url(uri)
    if result is None:
        return None
    parsed, port = result
    if not parsed.username:
        return None
    params = _query(parsed)
    node = ProxyNode(
        type='anytls',
        tag=_full_unquote(parsed.fragment) or 'anytls',
        server=parsed.hostname or '',
        port=port,
        password=urllib.parse.unquote(parsed.username),
    )
    _apply_tls(node, params, default_enabled=params.get('security', 'tls') != 'none')
    return node


def _parse_socks(uri: str) -> Optional[ProxyNode]:
    """Parse a SOCKS4, SOCKS4a, or SOCKS5 endpoint URI."""
    result = _parsed_url(uri, default_port=1080)
    if result is None:
        return None
    parsed, port = result
    scheme = parsed.scheme.lower()
    version = {'socks4': '4', 'socks4a': '4a', 'socks5': '5'}.get(scheme, '5')
    params = _query(parsed)
    return ProxyNode(
        type='socks',
        tag=_full_unquote(parsed.fragment) or scheme,
        server=parsed.hostname or '',
        port=port,
        username=urllib.parse.unquote(parsed.username or ''),
        password=urllib.parse.unquote(parsed.password or ''),
        version=version,
        network=params.get('network', '') if params.get('network') in {'tcp', 'udp'} else '',
    )


def _parse_http_proxy(uri: str) -> Optional[ProxyNode]:
    """Parse an authenticated HTTP or HTTPS CONNECT proxy endpoint URI."""
    result = _parsed_url(uri)
    if result is None:
        return None
    parsed, port = result
    if parsed.path not in {'', '/'} or not parsed.username:
        return None
    return ProxyNode(
        type='http',
        tag=_full_unquote(parsed.fragment) or parsed.scheme.lower(),
        server=parsed.hostname or '',
        port=port,
        username=urllib.parse.unquote(parsed.username),
        password=urllib.parse.unquote(parsed.password or ''),
        tls_enabled=parsed.scheme.lower() == 'https',
        tls_server_name=parsed.hostname or '',
    )


def _parse_ssh(uri: str) -> Optional[ProxyNode]:
    """Parse an SSH proxy endpoint URI."""
    result = _parsed_url(uri, default_port=22)
    if result is None:
        return None
    parsed, port = result
    params = _query(parsed)
    user = urllib.parse.unquote(parsed.username or params.get('user', '') or 'root')
    return ProxyNode(
        type='ssh',
        tag=_full_unquote(parsed.fragment) or 'ssh',
        server=parsed.hostname or '',
        port=port,
        username=user,
        password=urllib.parse.unquote(parsed.password or params.get('password', '')),
    )


def _parse_shadowtls(uri: str) -> Optional[ProxyNode]:
    """Parse a ShadowTLS endpoint URI into a proxy node."""
    result = _parsed_url(uri)
    if result is None:
        return None
    parsed, port = result
    params = _query(parsed)
    version = params.get('version', '3') or '3'
    if version not in {'1', '2', '3'}:
        return None
    password = urllib.parse.unquote(parsed.username or params.get('password', ''))
    if version in {'2', '3'} and not password:
        return None
    node = ProxyNode(
        type='shadowtls',
        tag=_full_unquote(parsed.fragment) or 'shadowtls',
        server=parsed.hostname or '',
        port=port,
        password=password,
        version=version,
    )
    _apply_tls(node, params, default_enabled=True)
    return node


def _parse_naive(uri: str) -> Optional[ProxyNode]:
    """Parse a NaiveProxy endpoint URI into a proxy node."""
    result = _parsed_url(uri, default_port=443)
    if result is None:
        return None
    parsed, port = result
    if not parsed.username or parsed.password is None:
        return None
    params = _query(parsed)
    return ProxyNode(
        type='naive',
        tag=_full_unquote(parsed.fragment) or 'naive',
        server=parsed.hostname or '',
        port=port,
        username=urllib.parse.unquote(parsed.username),
        password=urllib.parse.unquote(parsed.password),
        naive_quic=params.get('quic', '0').lower() in {'1', 'true', 'yes'},
        tls_enabled=True,
        tls_server_name=params.get('sni', '') or (parsed.hostname or ''),
    )


def parse_proxy_uri(uri: str) -> Optional[ProxyNode]:
    """Parse one safely representable proxy share URI into a normalized node."""
    uri = uri.strip()
    lower = uri.lower()
    if lower.startswith('vmess://'):
        return _parse_vmess(uri)
    if lower.startswith('vless://'):
        return _parse_vless_or_trojan(uri, 'vless')
    if lower.startswith('trojan://'):
        return _parse_vless_or_trojan(uri, 'trojan')
    if lower.startswith('ss://'):
        return _parse_shadowsocks(uri)
    if lower.startswith('hysteria2+realm://') or lower.startswith('hysteria2+realm+http://'):
        return _parse_hysteria2_realm(uri)
    if lower.startswith('hysteria2://') or lower.startswith('hy2://'):
        return _parse_hysteria2(uri)
    if lower.startswith('hysteria://'):
        return _parse_hysteria1(uri)
    if lower.startswith('tuic://'):
        return _parse_tuic(uri)
    if lower.startswith('anytls://'):
        return _parse_anytls(uri)
    if lower.startswith(('socks://', 'socks4://', 'socks4a://', 'socks5://')):
        return _parse_socks(uri)
    if lower.startswith(('http://', 'https://')):
        return _parse_http_proxy(uri)
    if lower.startswith('ssh://'):
        return _parse_ssh(uri)
    if lower.startswith('shadowtls://'):
        return _parse_shadowtls(uri)
    if lower.startswith(('naive+https://', 'naive://')):
        return _parse_naive(uri)
    return None


def _build_tls(node: ProxyNode) -> dict[str, Any]:
    """Build the sing-box TLS object for a normalized proxy node."""
    if not node.tls_enabled:
        return {}
    tls: dict[str, Any] = {'enabled': True}
    if node.tls_server_name:
        tls['server_name'] = node.tls_server_name
    if node.tls_insecure:
        tls['insecure'] = True
    if node.tls_alpn:
        tls['alpn'] = node.tls_alpn
    if node.tls_utls_fingerprint:
        tls['utls'] = {'enabled': True, 'fingerprint': node.tls_utls_fingerprint}
    if node.tls_reality_public_key:
        reality: dict[str, Any] = {'enabled': True, 'public_key': node.tls_reality_public_key}
        if node.tls_reality_short_id:
            reality['short_id'] = node.tls_reality_short_id
        tls['reality'] = reality
    return tls


def _build_transport(node: ProxyNode) -> dict[str, Any]:
    """Build a sing-box V2Ray transport object for a proxy node."""
    if not node.transport_type:
        return {}
    transport: dict[str, Any] = {'type': node.transport_type}
    if node.transport_type == 'ws':
        if node.transport_path:
            transport['path'] = node.transport_path
        if node.transport_host:
            transport['headers'] = {'Host': node.transport_host[0]}
    elif node.transport_type == 'grpc':
        transport['service_name'] = node.transport_service_name or 'grpc'
    elif node.transport_type == 'http':
        if node.transport_host:
            transport['host'] = node.transport_host
        if node.transport_path:
            transport['path'] = node.transport_path
    elif node.transport_type == 'httpupgrade':
        if node.transport_host:
            transport['host'] = node.transport_host[0]
        if node.transport_path:
            transport['path'] = node.transport_path
    return transport


def _current_server_ports(values: list[str]) -> list[str]:
    """Convert port ranges into sing-box current range syntax."""
    current = []
    for value in values:
        token = value.strip()
        if re.fullmatch('\\d+-\\d+', token):
            token = token.replace('-', ':', 1)
        if token:
            current.append(token)
    return current


def build_outbound(node: ProxyNode, *, resolver_tag: str = 'google') -> dict[str, Any]:
    """Render one normalized proxy node as a sing-box outbound."""
    outbound: dict[str, Any] = {'type': node.type, 'tag': node.tag}
    if node.realm_server_url:
        outbound['realm'] = {
            'server_url': node.realm_server_url,
            'token': node.realm_token,
            'realm_id': node.realm_id,
            'stun_servers': node.realm_stun_servers,
        }
    else:
        outbound['server'] = node.server
        ports = _current_server_ports(node.server_ports) if node.type == 'hysteria2' else []
        if ports:
            outbound['server_ports'] = ports
        else:
            outbound['server_port'] = node.port
        if node.server and not _is_ip(node.server):
            outbound['domain_resolver'] = resolver_tag
    if node.type == 'vmess':
        outbound.update(
            uuid=node.uuid,
            security=node.security,
            alter_id=node.alter_id,
            global_padding=False,
            authenticated_length=True,
        )
        if node.packet_encoding:
            outbound['packet_encoding'] = node.packet_encoding
    elif node.type == 'vless':
        outbound['uuid'] = node.uuid
        if node.flow:
            outbound['flow'] = node.flow
        if node.packet_encoding:
            outbound['packet_encoding'] = node.packet_encoding
    elif node.type == 'trojan':
        outbound['password'] = node.password
    elif node.type == 'shadowsocks':
        outbound.update(method=node.method, password=node.password)
        if node.plugin:
            outbound['plugin'] = node.plugin
            if node.plugin_opts:
                outbound['plugin_opts'] = node.plugin_opts
    elif node.type == 'hysteria':
        outbound.update(auth_str=node.password, up_mbps=node.up_mbps, down_mbps=node.down_mbps)
        if node.obfs_password:
            outbound['obfs'] = node.obfs_password
    elif node.type == 'hysteria2':
        outbound['password'] = node.password
        if node.up_mbps:
            outbound['up_mbps'] = node.up_mbps
        if node.down_mbps:
            outbound['down_mbps'] = node.down_mbps
        if node.obfs_type and node.obfs_password:
            outbound['obfs'] = {'type': node.obfs_type, 'password': node.obfs_password}
    elif node.type == 'tuic':
        outbound['uuid'] = node.uuid
        if node.password:
            outbound['password'] = node.password
        outbound.update(
            congestion_control=node.congestion_control,
            udp_relay_mode='native',
            zero_rtt_handshake=False,
            heartbeat='10s',
        )
    elif node.type == 'anytls':
        outbound.update(
            password=node.password,
            idle_session_check_interval='30s',
            idle_session_timeout='30s',
        )
    elif node.type == 'socks':
        outbound['version'] = node.version or '5'
        if node.username:
            outbound['username'] = node.username
        if node.password:
            outbound['password'] = node.password
    elif node.type == 'http':
        if node.username:
            outbound['username'] = node.username
        if node.password:
            outbound['password'] = node.password
    elif node.type == 'ssh':
        outbound['user'] = node.username or 'root'
        if node.password:
            outbound['password'] = node.password
    elif node.type == 'shadowtls':
        outbound['version'] = int(node.version or '3')
        if node.password:
            outbound['password'] = node.password
    elif node.type == 'naive':
        outbound['username'] = node.username
        outbound['password'] = node.password
        if node.naive_quic:
            outbound['quic'] = True
    if node.network:
        outbound['network'] = node.network
    tls = _build_tls(node)
    if tls:
        outbound['tls'] = tls
    transport = _build_transport(node)
    if transport and node.type in {'vmess', 'vless', 'trojan'}:
        outbound['transport'] = transport
    return outbound


def _unique_tag(base: str, seen: set[str]) -> str:
    """Return a unique outbound tag while preserving a readable base."""
    base = base.strip() or 'proxy'
    candidate = base
    index = 1
    while candidate in seen:
        candidate = f'{base}-{index}'
        index += 1
    seen.add(candidate)
    return candidate


def build_singbox_config(
    outbounds: list[dict[str, Any]],
    *,
    listen: str = '127.0.0.1',
    mixed_port: int = 2080,
    tun_enabled: bool = False,
) -> dict[str, Any]:
    """Build a complete sing-box client configuration."""
    proxy_tags = [outbound['tag'] for outbound in outbounds]
    selector_targets = (['auto'] if proxy_tags else []) + proxy_tags + ['direct']
    config: dict[str, Any] = {
        'log': {'level': 'info', 'timestamp': True},
        'dns': {
            'servers': [
                {
                    'type': 'tls',
                    'tag': 'google',
                    'server': '8.8.8.8',
                    'server_port': 853,
                    'tls': {'enabled': True, 'server_name': 'dns.google'},
                },
                {'type': 'local', 'tag': 'local'},
            ],
            'final': 'google',
            'strategy': 'prefer_ipv4',
            'optimistic': True,
            'reverse_mapping': True,
        },
        'inbounds': [
            {
                'type': 'mixed',
                'tag': 'mixed-in',
                'listen': listen,
                'listen_port': mixed_port,
                'set_system_proxy': False,
            }
        ],
        'outbounds': [
            {
                'type': 'selector',
                'tag': 'select',
                'outbounds': selector_targets,
                'default': 'auto' if proxy_tags else 'direct',
            }
        ]
        + outbounds
        + [{'type': 'direct', 'tag': 'direct'}],
        'route': {
            'rules': [
                {'ip_is_private': True, 'action': 'route', 'outbound': 'direct'},
                {'protocol': 'dns', 'action': 'hijack-dns'},
            ],
            'final': 'select',
            'auto_detect_interface': True,
            'default_domain_resolver': 'google',
        },
    }
    if proxy_tags:
        config['outbounds'].insert(1, {'type': 'urltest', 'tag': 'auto', 'outbounds': proxy_tags})
    if tun_enabled:
        config['inbounds'].insert(
            0,
            {
                'type': 'tun',
                'tag': 'tun-in',
                'address': ['172.19.0.1/30', 'fdfe:dcba:9876::1/126'],
                'mtu': 9000,
                'auto_route': True,
                'strict_route': True,
                'stack': 'system',
                'dns_mode': 'hijack',
                'dns_address': ['172.19.0.2', 'fdfe:dcba:9876::2'],
            },
        )
    return config


def config_from_uris(
    uris: list[str],
    *,
    listen: str = '127.0.0.1',
    mixed_port: int = 2080,
    tun_enabled: bool = False,
) -> dict[str, Any]:
    """Parse share URIs and render a sing-box client configuration."""
    outbounds: list[dict[str, Any]] = []
    seen_tags = set(_RESERVED_TAGS)
    for uri in uris:
        uri = uri.strip()
        if not uri or uri.startswith('#'):
            continue
        node = parse_proxy_uri(uri)
        if node is None:
            continue
        node.tag = _unique_tag(node.tag or node.type, seen_tags)
        outbounds.append(build_outbound(node))
    return build_singbox_config(outbounds, listen=listen, mixed_port=mixed_port, tun_enabled=tun_enabled)


def build_singbox_config_bytes(text: str) -> bytes:
    """Render proxy text as UTF-8 sing-box JSON bytes."""
    try:
        config = config_from_uris(text.splitlines())
    except AttributeError:
        return b''
    proxy_outbounds = [
        outbound
        for outbound in config.get('outbounds', [])
        if outbound.get('type') not in {'selector', 'urltest', 'direct'}
    ]
    if not proxy_outbounds:
        return b''
    return json.dumps(config, indent=2, ensure_ascii=False).encode('utf-8')
