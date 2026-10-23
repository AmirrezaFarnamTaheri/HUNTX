"""Upgrade observations and preserve independent provenance and health evidence."""
import hashlib
import json

from huntx.formats.npvt import canonical_proxy_identity
from huntx.state.db import open_db

URI = 'trojan://test@edge.example.com:443'


def test_v13_rekeys_aliases_preserving_revocation_probe_history_and_receipts(tmp_path):
    path = tmp_path / 'state.db'
    db = open_db(path)
    canonical_hash = hashlib.sha256(canonical_proxy_identity(URI).encode()).hexdigest()
    with db.connect() as conn:
        for number, line in enumerate([URI, URI + '?type=tcp'], 1):
            digest = str(number) * 64
            conn.execute('INSERT INTO records (source_file_hash, record_type, unique_hash, data_json) '
                         'VALUES (?, ?, ?, ?)', (str(number), 'npvt', digest, json.dumps({'line': line})))
            conn.execute('INSERT INTO proxy_lifecycle (unique_hash, record_type, lifecycle_status, '
                         'first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?)',
                         (digest, 'npvt', 'revoked' if number == 1 else 'active', number, number + 10))
            conn.execute('INSERT INTO proxy_probe_history (probe_id, unique_hash, record_type, '
                         'vantage_id, checked_at, success) VALUES (?, ?, ?, ?, ?, ?)',
                         (str(number), digest, 'npvt', 'vantage', number, 0))
        conn.execute("INSERT INTO published_artifacts (route_name, artifact_hash) VALUES ('route', 'receipt')")
        conn.execute('PRAGMA user_version = 12')
    upgraded = open_db(path)
    with upgraded.connect() as conn:
        assert {r['unique_hash'] for r in conn.execute('SELECT * FROM records')} == {canonical_hash}
        assert conn.execute('SELECT COUNT(*) FROM records').fetchone()[0] == 2
        lifecycle = conn.execute('SELECT * FROM proxy_lifecycle').fetchone()
        assert lifecycle['lifecycle_status'] == 'revoked'
        assert lifecycle['first_seen_at'] == 1 and lifecycle['last_seen_at'] == 12
        assert {r['unique_hash'] for r in conn.execute('SELECT * FROM proxy_probe_history')} == {canonical_hash}
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert conn.execute('SELECT artifact_hash FROM published_artifacts').fetchone()[0] == 'receipt'
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 13
    open_db(path)  # Reopening must not re-key or duplicate the history again.
    with upgraded.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM proxy_probe_history').fetchone()[0] == 2


def test_v13_splits_legacy_collision_without_aborting_or_reusing_probe_verdict(tmp_path):
    path = tmp_path / 'collision.db'
    db = open_db(path)
    base = 'vless://11111111-2222-4333-8444-555555555555@edge.example.com:443'
    lines = [
        base + '?security=TLS&type=ws&path=%2Fa&sni=CDN.Example',
        base + '?security=tls&type=ws&path=%2Fa&sni=cdn.example',
        base + '?security=tls&type=ws&path=%2Fb&sni=cdn.example',
    ]
    legacy = 'a' * 64
    with db.connect() as conn:
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('INSERT INTO proxy_lifecycle (unique_hash, record_type, lifecycle_status, '
                     'first_seen_at, last_seen_at, authenticated_failures, consecutive_failures) '
                     'VALUES (?, ?, ?, ?, ?, ?, ?)', (legacy, 'npvt', 'revoked', 1, 9, 4, 3))
        conn.execute('INSERT INTO proxy_probe_history (probe_id, unique_hash, record_type, '
                     'vantage_id, checked_at, success) VALUES (?, ?, ?, ?, ?, ?)',
                     ('legacy-probe', legacy, 'npvt', 'old-vantage', 8, 1))
        conn.execute('INSERT INTO record_verdicts (unique_hash, record_type, syntax_status, parser_version, '
                     'probe_status, probe_checked_at, probe_expires_at, policy_status, policy_version, '
                     'policy_tier, reason_codes_json, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                     (legacy, 'npvt', 'valid', 'old', 'healthy', 8, 99, 'allowed', 'old', 'default', '[]', 8))
        for index, line in enumerate(lines):
            conn.execute('INSERT INTO records (source_file_hash, record_type, unique_hash, data_json) '
                         'VALUES (?, ?, ?, ?)', (str(index), 'npvt', legacy, json.dumps({'line': line})))
        conn.execute('PRAGMA user_version = 12')

    upgraded = open_db(path)
    expected = {hashlib.sha256(canonical_proxy_identity(line).encode()).hexdigest() for line in lines}
    assert len(expected) == 2  # SNI/security case variants canonicalize together; path variants stay distinct.
    with upgraded.connect() as conn:
        assert {row['unique_hash'] for row in conn.execute('SELECT * FROM records')} == expected
        lifecycles = conn.execute('SELECT * FROM proxy_lifecycle ORDER BY unique_hash').fetchall()
        assert len(lifecycles) == 2
        assert all(row['lifecycle_status'] == 'revoked' for row in lifecycles)
        assert all(row['authenticated_failures'] == 4 and row['consecutive_failures'] == 3 for row in lifecycles)
        verdicts = conn.execute('SELECT * FROM record_verdicts').fetchall()
        assert {row['unique_hash'] for row in verdicts} == expected
        assert all(row['probe_status'] == 'unknown' and row['probe_expires_at'] is None for row in verdicts)
        history = conn.execute('SELECT * FROM proxy_probe_history').fetchall()
        assert len(history) == 1 and history[0]['unique_hash'] in expected
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 13
