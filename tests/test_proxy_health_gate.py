"""Publication must fail closed without node-attributed, fresh HTTPS proof."""
import time
from unittest.mock import MagicMock

import pytest

from huntx.core import proxy_health as health
from huntx.formats.npvt import NpvtHandler

BASE = 'trojan://password@edge.example.com:443'


@pytest.fixture(autouse=True)
def isolated_engine_bootstrap(monkeypatch):
    monkeypatch.setattr(health, '_verify_engine', lambda _binary: None)


def test_engine_config_has_one_node_and_no_bypass():
    config = health.probe_config(BASE, 19080)
    assert config['inbounds'][0]['listen'] == '127.0.0.1'
    assert len(config['outbounds']) == 1
    assert config['outbounds'][0]['type'] == 'trojan'
    assert config['route']['final'] == config['outbounds'][0]['tag']
    assert not config['route'].get('rules')
    assert health.probe_config('opaque://unsupported', 19080) is None


@pytest.mark.parametrize('status,body,expected', [(204, b'', True), (200, b'', False), (204, b'x', False)])
def test_https_check_requires_verified_tls_and_expected_response(monkeypatch, status, body, expected):
    constructor = MagicMock()
    connection = constructor.return_value
    connection.getresponse.return_value.status = status
    connection.getresponse.return_value.read.return_value = body
    monkeypatch.setattr(health.http.client, 'HTTPSConnection', constructor)
    monkeypatch.setenv('NO_PROXY', '*')  # Must not bypass the explicitly selected tunnel.
    assert health._https_through_proxy(19080, ('target.example', '/generate_204', 204), 2) is expected
    connection.set_tunnel.assert_called_once_with('target.example', 443)
    context = constructor.call_args.kwargs['context']
    assert context.check_hostname and context.verify_mode == health.ssl.CERT_REQUIRED
    connection.close.assert_called_once()


def test_engine_cleanup_and_failed_authenticated_path_do_not_accept_open_tcp(monkeypatch):
    child = MagicMock()
    child.poll.return_value = None
    monkeypatch.setattr(health.subprocess, 'Popen', MagicMock(return_value=child))
    monkeypatch.setattr(health.socket, 'create_connection', MagicMock())
    attempts = MagicMock(return_value=False)
    monkeypatch.setattr(health, '_https_through_proxy', attempts)
    assert health.check_proxy(BASE, '/fake/engine')['ok'] is False
    assert attempts.call_count == 2
    child.terminate.assert_called_once()
    child.wait.assert_called_once()


def test_missing_engine_prevents_publication_instead_of_falling_back(monkeypatch):
    monkeypatch.setenv('HUNTX_REQUIRE_PROXY_HEALTH', '1')
    monkeypatch.setattr(health.shutil, 'which', lambda _: None)
    with pytest.raises(RuntimeError, match='require.*sing-box'):
        NpvtHandler().build([{'data': {'line': BASE}}])


@pytest.mark.parametrize('result', [
    {'ok': False}, {'ok': 'true'}, {'ok': True},
    {'ok': True, 'checked_at': 0, 'latency_ms': 2},
    {'ok': True, 'checked_at': float('nan'), 'latency_ms': 2},
])
def test_failed_unknown_malformed_and_stale_probes_are_excluded(monkeypatch, result):
    monkeypatch.setattr(health.shutil, 'which', lambda _: '/fake/engine')
    monkeypatch.setattr(health, 'check_proxy', lambda *_a, **_k: result)
    assert health.verified_records([{'data': {'line': BASE}}]) == []


def test_only_fresh_success_is_admitted_and_equivalent_nodes_are_checked_once(monkeypatch):
    monkeypatch.setattr(health.shutil, 'which', lambda _: '/fake/engine')
    checker = MagicMock(side_effect=lambda *_a, **_k: {
        'ok': True, 'checked_at': time.time(), 'latency_ms': 23,
        'reason': 'authenticated_https'})
    monkeypatch.setattr(health, 'check_proxy', checker)
    records = health.verified_records([{'data': {'line': BASE + '#one'}}, {'data': {'line': BASE + '#two'}}])
    assert checker.call_count == 1 and len(records) == 1
    fields = records[0]['data']
    assert fields['probe_authenticated'] is True
    assert fields['probe_kind'] == 'protocol_authenticated'
    assert fields['probe_expires_at'] > time.time()


def test_engine_infrastructure_failure_aborts_build(monkeypatch):
    monkeypatch.setattr(health.shutil, 'which', lambda _: '/fake/engine')

    def unavailable(_binary):
        raise RuntimeError('engine unavailable')
    monkeypatch.setattr(health, '_verify_engine', unavailable)
    with pytest.raises(RuntimeError, match='engine unavailable'):
        health.verified_records([{'data': {'line': BASE}}])
