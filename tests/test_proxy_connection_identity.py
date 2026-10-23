"""Dedup share-link defaults without merging different connection contracts."""
import base64
import json
from urllib.parse import unquote, urlsplit

import pytest

from huntx.formats.npvt import NpvtHandler, canonical_proxy_identity
from huntx.formats.common.singbox import build_singbox_config_bytes
from huntx.formats.common.xray import build_xray_config_bytes
from huntx.formats.common.clash import build_clash_subscription_bytes
from huntx.formats.common.nekobox import build_nekobox_outbounds_bytes

ID = '11111111-2222-4333-8444-555555555555'
BASE = f'vless://{ID}@edge.example.com:443'


@pytest.mark.parametrize('suffix', [
    '?type=tcp', '?type=raw', '?security=none', '?encryption=none',
    '?headerType=none', '?packetEncoding=xudp', '?allowInsecure=0&insecure=0',
])
def test_default_spellings_are_one_connection(suffix):
    assert canonical_proxy_identity(BASE) == canonical_proxy_identity(BASE + suffix)


def test_boolean_aliases_and_numeric_vmess_fields_are_equivalent():
    assert canonical_proxy_identity(BASE + '?security=tls&allowInsecure=1') == canonical_proxy_identity(
        BASE + '?security=tls&insecure=1')
    payload = {'add': 'edge.example.com', 'port': '443', 'id': ID, 'aid': '0', 'net': 'tcp', 'type': 'none'}
    other = {**payload, 'port': 443, 'aid': 0, 'ps': 'another name'}

    def uri(value):
        return 'vmess://' + base64.b64encode(json.dumps(value).encode()).decode()
    assert canonical_proxy_identity(uri(payload)) == canonical_proxy_identity(uri(other))


@pytest.mark.parametrize('suffix', [
    '?type=ws&path=%2Fa', '?security=tls', '?unknown=one',
    '?headerType=http', '?flow=xtls-rprx-vision', '?network=udp',
    '?type=ws&type=tcp', '?ech=secret', '?encryption=mlkem768x25519plus.native',
])
def test_connection_extensions_remain_distinct(suffix):
    assert canonical_proxy_identity(BASE) != canonical_proxy_identity(BASE + suffix)


@pytest.mark.parametrize('render', [build_singbox_config_bytes, build_xray_config_bytes,
                                    build_nekobox_outbounds_bytes, build_clash_subscription_bytes])
def test_client_serializers_remove_duplicates_after_conversion(render):
    # The URI layer retains unmodeled extensions; this client serializer does
    # not emit them. Its final connection objects must therefore appear once.
    feed = BASE + '?security=tls&type=ws&extra=one#A\n' + BASE + '?security=tls&type=ws&extra=two#B\n'
    payload = render(feed)
    if render is build_clash_subscription_bytes:
        assert sum(line.lstrip().startswith(b'- ') for line in payload.splitlines()) == 1
    else:
        value = json.loads(payload)
        nodes = value if isinstance(value, list) else value['outbounds']
        assert len(nodes) == 1


def test_clean_labels_keep_country_and_distinct_connection_suffixes(monkeypatch):
    monkeypatch.setenv('HUNTX_REMARK_STYLE', 'evidence')
    records = [{'data': {'line': BASE + suffix, 'country_hint': 'DE',
                         'country_hint_source': 'source_remark'}}
               for suffix in ('?type=ws&path=%2Fa', '?type=ws&path=%2Fb')]
    names = [unquote(urlsplit(line).fragment)
             for line in NpvtHandler().build(records).decode().splitlines()]
    assert len(names) == len(set(names)) == 2
    assert all(name.startswith('🇩🇪 VLESS-WS | ') and '?' not in name for name in names)
    assert any('No.2' in name for name in names)


def test_dormant_tls_fields_do_not_duplicate_plain_connections():
    assert canonical_proxy_identity(BASE) == canonical_proxy_identity(BASE + '?sni=unused.example')
    assert canonical_proxy_identity(BASE + '?security=tls&sni=one.example') != canonical_proxy_identity(
        BASE + '?security=tls&sni=two.example')


def test_boolean_true_alias_does_not_merge_into_verified_tls():
    secure = BASE + '?security=tls'
    bypass = secure + '&allowInsecure=true'
    assert canonical_proxy_identity(bypass) == canonical_proxy_identity(secure + '&insecure=1')
    assert canonical_proxy_identity(secure) != canonical_proxy_identity(bypass)
