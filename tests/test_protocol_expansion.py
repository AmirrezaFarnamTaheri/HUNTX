import json
from unittest.mock import Mock

from huntx.core.router import decide_format
from huntx.formats.common.singbox import config_from_uris, parse_proxy_uri
from huntx.formats.npvt import NpvtHandler
from huntx.formats.proxy_uri_validator import validate_proxy_uri
from huntx.pipeline.build import BuildPipeline


def _outbound(config, outbound_type):
    """Return the first outbound with the requested type."""
    return next(item for item in config['outbounds'] if item.get('type') == outbound_type)


def test_hysteria1_official_uri_is_valid_and_exportable():
    uri = (
        'hysteria://h1.example.com:443?protocol=udp&auth=secret'
        '&peer=h1.example.com&upmbps=25&downmbps=80&obfs=xplus'
        '&obfsParam=cover#H1'
    )
    assert validate_proxy_uri(uri)
    node = parse_proxy_uri(uri)
    assert node is not None
    assert node.type == 'hysteria'
    config = config_from_uris([uri])
    outbound = _outbound(config, 'hysteria')
    assert outbound['auth_str'] == 'secret'
    assert outbound['up_mbps'] == 25
    assert outbound['down_mbps'] == 80
    assert outbound['obfs'] == 'cover'
    assert outbound['tls']['server_name'] == 'h1.example.com'


def test_hysteria1_non_quic_legacy_transport_is_preserved_but_not_misrendered():
    uri = (
        'hysteria://h1.example.com:443?protocol=faketcp&auth=secret'
        '&upmbps=25&downmbps=80'
    )
    assert validate_proxy_uri(uri)
    assert parse_proxy_uri(uri) is None


def test_hysteria2_default_port_and_authority_multiport_are_supported():
    default_port = 'hysteria2://secret@h2.example.com/?sni=h2.example.com#H2'
    assert validate_proxy_uri(default_port)
    node = parse_proxy_uri(default_port)
    assert node is not None
    assert node.port == 443

    multi = (
        'hysteria2://secret@h2.example.com:443,5000-6000/'
        '?sni=h2.example.com&obfs=gecko&obfs-password=cover#H2Multi'
    )
    assert validate_proxy_uri(multi)
    config = config_from_uris([multi])
    outbound = _outbound(config, 'hysteria2')
    assert outbound['server_ports'] == ['443', '5000:6000']
    assert 'server_port' not in outbound
    assert outbound['obfs'] == {'type': 'gecko', 'password': 'cover'}


def test_hysteria2_userpass_preserves_colon_in_authentication():
    uri = 'hy2://alice:secret@h2.example.com:443/?sni=h2.example.com'
    assert validate_proxy_uri(uri)
    node = parse_proxy_uri(uri)
    assert node is not None
    assert node.password == 'alice:secret'


def test_hysteria2_realm_uri_maps_to_realm_object_without_server_fields():
    uri = (
        'hysteria2+realm://token@realm.example.com/my-room'
        '?auth=hy-password&stun=stun1.example.com:3478&stun=stun2.example.com:3478'
        '&sni=cert.example.com#Realm'
    )
    assert validate_proxy_uri(uri)
    node = parse_proxy_uri(uri)
    assert node is not None
    assert node.realm_server_url == 'https://realm.example.com'
    config = config_from_uris([uri])
    outbound = _outbound(config, 'hysteria2')
    assert 'server' not in outbound
    assert 'server_port' not in outbound
    assert outbound['password'] == 'hy-password'
    assert outbound['realm']['server_url'] == 'https://realm.example.com'
    assert outbound['realm']['token'] == 'token'
    assert outbound['realm']['realm_id'] == 'my-room'
    assert outbound['realm']['stun_servers'] == [
        'stun1.example.com:3478',
        'stun2.example.com:3478',
    ]


def test_socks4a_http_https_ssh_shadowtls_and_naive_are_exported():
    uris = [
        'socks4a://proxy.example.com:1080#S4A',
        'http://alice:secret@http.example.com:8080#HTTP',
        'https://alice:secret@https.example.com:8443#HTTPS',
        'ssh://root:secret@ssh.example.com:22#SSH',
        'shadowtls://secret@st.example.com:443?version=3&sni=cdn.example.com#ST',
        'naive+https://alice:secret@naive.example.com:443#Naive',
    ]
    assert all(validate_proxy_uri(uri) for uri in uris)
    config = config_from_uris(uris)

    socks = _outbound(config, 'socks')
    assert socks['version'] == '4a'

    http_nodes = [item for item in config['outbounds'] if item.get('type') == 'http']
    assert len(http_nodes) == 2
    assert any(item.get('tls', {}).get('enabled') for item in http_nodes)

    ssh = _outbound(config, 'ssh')
    assert ssh['user'] == 'root'
    assert ssh['password'] == 'secret'

    shadowtls = _outbound(config, 'shadowtls')
    assert shadowtls['version'] == 3
    assert shadowtls['password'] == 'secret'

    naive = _outbound(config, 'naive')
    assert naive['username'] == 'alice'
    assert naive['password'] == 'secret'
    assert naive['tls']['enabled'] is True


def test_ordinary_web_url_does_not_trigger_proxy_classification():
    assert decide_format('message.txt', b'read https://example.com:443/docs for help') == 'opaque_bundle'
    assert not validate_proxy_uri('https://example.com:443/docs')


def test_authenticated_http_proxy_is_detected_and_npvt_parses_it():
    uri = 'https://alice:secret@proxy.example.com:8443'
    assert decide_format('message.txt', uri.encode()) == 'npvt'
    records = NpvtHandler().parse(uri.encode(), {})
    assert len(records) == 1
    assert records[0]['data']['line'] == uri


def test_wireguard_is_preserved_as_valid_input_but_not_emitted_as_removed_outbound():
    uri = 'wg://secret@wg.example.com:51820'
    assert validate_proxy_uri(uri)
    assert parse_proxy_uri(uri) is None
    config = config_from_uris([uri])
    assert not any(item.get('type') == 'wireguard' for item in config['outbounds'])


def test_decoded_json_counts_new_protocols():
    pipeline = BuildPipeline(Mock(), Mock(), Mock())
    raw = '\n'.join(
        [
            'socks4a://proxy.example.com:1080',
            'ssh://root:secret@ssh.example.com:22',
            'shadowtls://secret@st.example.com:443?version=3&sni=cdn.example.com',
            'naive+https://alice:secret@naive.example.com:443',
            'https://alice:secret@http.example.com:8443',
        ]
    )
    decoded = json.loads(pipeline._decode_proxy_text(raw).decode())
    assert decoded['protocols'] == {
        'socks': 1,
        'ssh': 1,
        'shadowtls': 1,
        'naive': 1,
        'http': 1,
    }
