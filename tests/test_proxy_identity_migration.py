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
