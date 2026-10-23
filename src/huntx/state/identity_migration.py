"""Re-key stored proxy observations without dropping provenance or health history."""
from __future__ import annotations

import hashlib
import json
import sqlite3


def migrate_proxy_identities(conn: sqlite3.Connection) -> int:
    # Import lazily: database construction happens after the format registry loads.
    from ..formats.npvt import canonical_proxy_identity, strip_proxy_remark
    from ..formats.proxy_uri_validator import validate_proxy_uri

    rows = conn.execute(
        "SELECT id, unique_hash, record_type, data_json FROM records "
        "WHERE record_type IN ('npvt', 'npvtsub')"
    ).fetchall()
    changed = 0
    groups: dict[tuple[str, str], dict[str, list[sqlite3.Row]]] = {}
    for row in rows:
        try:
            data = json.loads(row['data_json'])
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get('line'), str):
            continue
        if not validate_proxy_uri(data['line']):
            continue
        line = strip_proxy_remark(data['line'])
        digest = hashlib.sha256(canonical_proxy_identity(line).encode()).hexdigest()
        old_identity = (row['unique_hash'], row['record_type'])
        groups.setdefault(old_identity, {}).setdefault(digest, []).append(row)
        data['line'] = line
        conn.execute('UPDATE records SET unique_hash = ?, data_json = ? WHERE id = ?',
                     (digest, json.dumps(data, ensure_ascii=False, sort_keys=True), row['id']))
        changed += int(old_identity[0] != digest)

    for (old, record_type), targets in groups.items():
        digests = sorted(targets)
        # A legacy hash may have represented several distinct connections (for
        # example, case-folded SNI/security variants). Carry lifecycle state to
        # every target conservatively, but never copy a probe verdict to a
        # connection that was not independently checked.
        prior = conn.execute('SELECT * FROM proxy_lifecycle WHERE unique_hash = ? AND record_type = ?',
                             (old, record_type)).fetchone()
        if prior is not None:
            for digest in digests:
                current = conn.execute('SELECT * FROM proxy_lifecycle WHERE unique_hash = ? AND record_type = ?',
                                       (digest, record_type)).fetchone()
                value = dict(prior)
                value['unique_hash'] = digest
                value['last_probe_result'] = 'unverified'
                value['last_probe_at'] = None
                if current is not None:
                    value = dict(current)
                    value['unique_hash'] = digest
                    value['first_seen_at'] = min(prior['first_seen_at'], current['first_seen_at'])
                    value['last_seen_at'] = max(prior['last_seen_at'], current['last_seen_at'])
                    for key in ('authenticated_successes', 'authenticated_failures', 'consecutive_failures'):
                        value[key] = max(prior[key], current[key])
                    restrictive = ('revoked', 'dead', 'archived', 'suspect', 'degraded')
                    statuses = {prior['lifecycle_status'], current['lifecycle_status']}
                    value['lifecycle_status'] = next((status for status in restrictive if status in statuses),
                                                     current['lifecycle_status'])
                    value['last_probe_at'] = None
                    value['last_probe_result'] = 'unverified'
                columns = ', '.join(value)
                placeholders = ', '.join('?' for _ in value)
                updates = ', '.join(f'{key}=excluded.{key}' for key in value
                                    if key not in {'unique_hash', 'record_type'})
                conn.execute(f'INSERT INTO proxy_lifecycle ({columns}) VALUES ({placeholders}) '
                             f'ON CONFLICT(unique_hash, record_type) DO UPDATE SET {updates}', tuple(value.values()))

        verdicts = conn.execute('SELECT * FROM record_verdicts WHERE unique_hash = ? AND record_type = ?',
                                (old, record_type)).fetchall()
        for verdict in verdicts:
            for digest in digests:
                value = dict(verdict)
                value.update(unique_hash=digest, probe_status='unknown',
                             probe_checked_at=None, probe_expires_at=None)
                columns = ', '.join(value)
                placeholders = ', '.join('?' for _ in value)
                updates = ', '.join(f'{key}=excluded.{key}' for key in value
                                    if key not in {'unique_hash', 'record_type', 'policy_tier'})
                conn.execute(f'INSERT INTO record_verdicts ({columns}) VALUES ({placeholders}) '
                             f'ON CONFLICT(unique_hash, record_type, policy_tier) DO UPDATE SET {updates}',
                             tuple(value.values()))

        # probe_id is globally unique, so preserve the legacy history on one
        # deterministic target only; other split identities start unprobed.
        if digests:
            conn.execute('UPDATE proxy_probe_history SET unique_hash = ? '
                         'WHERE unique_hash = ? AND record_type = ?',
                         (digests[0], old, record_type))
        if old not in targets:
            conn.execute('DELETE FROM record_verdicts WHERE unique_hash = ? AND record_type = ?', (old, record_type))
            conn.execute('DELETE FROM proxy_lifecycle WHERE unique_hash = ? AND record_type = ?', (old, record_type))
    return changed
