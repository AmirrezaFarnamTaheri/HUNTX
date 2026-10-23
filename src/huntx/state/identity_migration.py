"""Re-key stored proxy observations without dropping provenance or health history."""
from __future__ import annotations

import hashlib
import json
import sqlite3


def migrate_proxy_identities(conn: sqlite3.Connection) -> int:
    # Import lazily: database construction happens after the format registry loads.
    from ..formats.npvt import canonical_proxy_identity, strip_proxy_remark
    from ..formats.proxy_uri_validator import validate_proxy_uri

    mappings: dict[tuple[str, str], str] = {}
    rows = conn.execute(
        "SELECT id, unique_hash, record_type, data_json FROM records "
        "WHERE record_type IN ('npvt', 'npvtsub')"
    ).fetchall()
    changed = 0
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
        previous = mappings.setdefault(old_identity, digest)
        if previous != digest:
            raise RuntimeError('Legacy proxy identity maps to conflicting connections')
        data['line'] = line
        conn.execute('UPDATE records SET unique_hash = ?, data_json = ? WHERE id = ?',
                     (digest, json.dumps(data, ensure_ascii=False, sort_keys=True), row['id']))
        changed += int(old_identity[0] != digest)

    for (old, record_type), new in mappings.items():
        if old == new:
            continue
        # A verdict for this same connection retains its freshness, never a new TTL.
        verdicts = conn.execute('SELECT * FROM record_verdicts WHERE unique_hash = ? AND record_type = ?',
                                (old, record_type)).fetchall()
        for row in verdicts:
            value = dict(row)
            value['unique_hash'] = new
            existing = conn.execute(
                'SELECT updated_at FROM record_verdicts WHERE unique_hash = ? AND record_type = ? AND policy_tier = ?',
                (new, record_type, value['policy_tier']),
            ).fetchone()
            if existing is None or value['updated_at'] > existing['updated_at']:
                columns = ', '.join(value)
                placeholders = ', '.join('?' for _ in value)
                conn.execute(f'INSERT OR REPLACE INTO record_verdicts ({columns}) VALUES ({placeholders})',
                             tuple(value.values()))
        conn.execute('DELETE FROM record_verdicts WHERE unique_hash = ? AND record_type = ?', (old, record_type))
        prior = conn.execute('SELECT * FROM proxy_lifecycle WHERE unique_hash = ? AND record_type = ?',
                             (old, record_type)).fetchone()
        if prior is None:
            continue
        current = conn.execute('SELECT * FROM proxy_lifecycle WHERE unique_hash = ? AND record_type = ?',
                               (new, record_type)).fetchone()
        value = dict(prior)
        value['unique_hash'] = new
        if current is not None:
            # Preserve the latest observation, all failure counters and any
            # explicit retirement. An alias must never revive a revoked proxy.
            value = dict(max((prior, current), key=lambda r: r['last_probe_at'] or 0))
            value['unique_hash'] = new
            value['first_seen_at'] = min(prior['first_seen_at'], current['first_seen_at'])
            value['last_seen_at'] = max(prior['last_seen_at'], current['last_seen_at'])
            for key in ('authenticated_successes', 'authenticated_failures', 'consecutive_failures'):
                value[key] = max(prior[key], current[key])
            for status in ('revoked', 'dead', 'archived'):
                if status in (prior['lifecycle_status'], current['lifecycle_status']):
                    value['lifecycle_status'] = status
                    break
        columns = ', '.join(value)
        placeholders = ', '.join('?' for _ in value)
        updates = ', '.join(f'{key}=excluded.{key}' for key in value if key not in {'unique_hash', 'record_type'})
        # UPSERT rather than REPLACE: existing history references this parent.
        conn.execute(f'INSERT INTO proxy_lifecycle ({columns}) VALUES ({placeholders}) '
                     f'ON CONFLICT(unique_hash, record_type) DO UPDATE SET {updates}', tuple(value.values()))
        conn.execute('UPDATE proxy_probe_history SET unique_hash = ? WHERE unique_hash = ? AND record_type = ?',
                     (new, old, record_type))
        conn.execute('DELETE FROM proxy_lifecycle WHERE unique_hash = ? AND record_type = ?', (old, record_type))
    return changed
