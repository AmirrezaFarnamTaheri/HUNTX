"""Stable, historical latest per-protocol subscriptions for every supported URI protocol.

These are historical discovery feeds, NOT authenticated working-proxy releases.
The oldest entries do not expire solely because of their age.
"""
from __future__ import annotations

import base64
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from huntx.core.router import _PROXY_SCHEMES
from huntx.formats.npvt import canonical_proxy_identity, strip_proxy_remark
from huntx.formats.proxy_uri_validator import validate_proxy_uri

LATEST_LIMIT = 200
PROTOCOL_LIMITS = {"vless": 150, "shadowsocks": 150}


def _limit_for_protocol(category: str) -> int:
    return PROTOCOL_LIMITS.get(category, LATEST_LIMIT)


# Normalize spelling/versions to user-facing protocol families. This is NOT a
# generic "others" bucket: every new router-supported scheme gets its own name.
_ALIASES = {
    "hy2": "hysteria2",
    "hysteria2+realm": "hysteria2",
    "hysteria2+realm+http": "hysteria2",
    "ss": "shadowsocks",
    "ssr": "shadowsocksr",
    "socks4": "socks",
    "socks4a": "socks",
    "socks5": "socks",
    "https": "http",
    "wg": "wireguard",
    "naive+https": "naive",
    "naive+quic": "naive",
    "mierus": "mieru",
}
_SUPPORTED_SCHEMES = frozenset(
    uri.removesuffix("://") for uri in _PROXY_SCHEMES
) | {"http", "https"}


def _category_for_scheme(scheme: str) -> str:
    return _ALIASES.get(scheme, scheme.replace("+", "-"))


PROTOCOL_CATEGORIES: tuple[str, ...] = tuple(sorted({
    _category_for_scheme(scheme) for scheme in _SUPPORTED_SCHEMES
}))


def protocol_for_uri(uri: str) -> str | None:
    """Return a separate canonical protocol label, only for safe known URIs."""
    if not isinstance(uri, str) or "://" not in uri:
        return None
    scheme = uri.split("://", 1)[0].lower()
    if scheme not in _SUPPORTED_SCHEMES or not validate_proxy_uri(uri):
        return None
    return _category_for_scheme(scheme)


def _newest_key(value: float | int | str) -> tuple[int, float | str]:
    """Match the historical publisher's newest-discovery ordering."""
    try:
        return (1, float(value))
    except (ValueError, TypeError, OverflowError):
        return (0, str(value))


def _identity(uri: str) -> str:
    """Collapse aliases without treating different credentials as equivalent."""
    scheme, separator, rest = uri.partition("://")
    if separator and scheme.lower() == "hy2":
        return canonical_proxy_identity("hysteria2://" + rest)
    return canonical_proxy_identity(uri)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _plain_bytes(uris: list[str]) -> bytes:
    return ("\n".join(uris) + "\n").encode("utf-8") if uris else b""


def _base64_bytes(plain: bytes) -> bytes:
    return base64.b64encode(plain) + b"\n" if plain else b""


def write_latest_subscriptions(
    destination: Path,
    manifest: dict[str, float | int | str],
    source_created_at: str,
) -> dict[str, Any]:
    """Publish latest per-protocol caps and their union, with deterministic metadata.

    No time filter is applied. Newest refers to the immutable first-discovery
    timestamp already stored by HUNTX's cumulative manifest.
    """
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir() or destination.is_symlink():
        raise ValueError("latest-subscription destination must be a directory")

    # The target is a dedicated generated directory: remove stale protocol
    # outputs when the supported scheme registry changes.
    for stale in destination.iterdir():
        if stale.is_symlink() or not stale.is_file() or stale.suffix not in {".txt", ".json"}:
            raise ValueError("unexpected file in latest-subscription directory")
        stale.unlink()

    grouped: dict[str, dict[str, tuple[str, float | int | str]]] = defaultdict(dict)
    for candidate, first_seen in sorted(manifest.items()):
        uri = strip_proxy_remark(candidate)
        category = protocol_for_uri(uri)
        if category is None:
            continue
        fingerprint = _identity(uri)
        previous = grouped[category].get(fingerprint)
        if previous is None:
            grouped[category][fingerprint] = (uri, first_seen)
        else:
            old_uri, old_seen = previous
            # Equivalent spellings retain first-seen history, but publish the
            # newest-discovered representative for latest-N selection.
            if (_newest_key(first_seen), uri) > (_newest_key(old_seen), old_uri):
                grouped[category][fingerprint] = (uri, first_seen)

    index: dict[str, Any] = {
        "schema_version": 1,
        "scope": "all_time_cumulative",
        "health_status": "historical_unverified",
        "generated_at": source_created_at,
        "latest_by": "first_seen",
        "limit_per_protocol": LATEST_LIMIT,
        "protocol_limits": PROTOCOL_LIMITS.copy(),
        "protocols": {},
    }
    selected: list[tuple[str, float | int | str]] = []
    for category in PROTOCOL_CATEGORIES:
        records = list(grouped[category].values())
        # Stable lexical order is a tie-breaker, not the primary ranking.
        records.sort(key=lambda row: row[0])
        records.sort(key=lambda row: _newest_key(row[1]), reverse=True)
        records = records[:_limit_for_protocol(category)]
        uris = [row[0] for row in records]
        raw = _plain_bytes(uris)
        (destination / f"{category}.txt").write_bytes(raw)
        (destination / f"{category}_base64.txt").write_bytes(_base64_bytes(raw))
        selected.extend(records)
        index["protocols"][category] = {
            "count": len(records),
            "file": f"{category}.txt",
            "base64_file": f"{category}_base64.txt",
            "sha256": _sha256(raw),
        }

    selected.sort(key=lambda row: row[0])
    selected.sort(key=lambda row: _newest_key(row[1]), reverse=True)
    aggregate = _plain_bytes([uri for uri, _ in selected])
    (destination / "all.txt").write_bytes(aggregate)
    (destination / "all_base64.txt").write_bytes(_base64_bytes(aggregate))
    index["aggregate"] = {
        "count": len(selected),
        "file": "all.txt",
        "base64_file": "all_base64.txt",
        "sha256": _sha256(aggregate),
    }
    (destination / "index.json").write_text(
        json.dumps(index, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    validate_latest_subscriptions(destination)
    return index


def validate_latest_subscriptions(directory: Path) -> dict[str, Any]:
    """Check every category and ensure the master is its exact deduplicated union."""
    index_path = directory / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid latest-subscription index") from exc
    if (
        not isinstance(index, dict)
        or index.get("schema_version") != 1
        or index.get("scope") != "all_time_cumulative"
        or index.get("health_status") != "historical_unverified"
        or index.get("limit_per_protocol") != LATEST_LIMIT
        or index.get("protocol_limits") != PROTOCOL_LIMITS
        or not isinstance(index.get("protocols"), dict)
        or set(index["protocols"]) != set(PROTOCOL_CATEGORIES)
        or not isinstance(index.get("aggregate"), dict)
    ):
        raise ValueError("invalid latest-subscription index fields")

    expected_files = {"index.json"}
    all_uris: set[str] = set()
    for category in (*PROTOCOL_CATEGORIES, "all"):
        entry = index["aggregate"] if category == "all" else index["protocols"][category]
        if not isinstance(entry, dict):
            raise ValueError("invalid latest-subscription category entry")
        plain_name = f"{category}.txt"
        encoded_name = f"{category}_base64.txt"
        if entry.get("file") != plain_name or entry.get("base64_file") != encoded_name:
            raise ValueError("invalid latest-subscription filenames")
        expected_files.update((plain_name, encoded_name))
        try:
            raw = (directory / plain_name).read_bytes()
            encoded = (directory / encoded_name).read_bytes()
            lines = raw.decode("utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ValueError("missing or invalid latest-subscription file") from exc
        if raw != _plain_bytes(lines):
            raise ValueError("noncanonical latest-subscription text bytes")
        if encoded != _base64_bytes(raw):
            raise ValueError("latest-subscription base64 mismatch")
        if entry.get("sha256") != _sha256(raw):
            raise ValueError("latest-subscription checksum mismatch")
        if type(entry.get("count")) is not int or entry["count"] != len(lines):
            raise ValueError("latest-subscription count mismatch")
        if category != "all":
            if len(lines) > _limit_for_protocol(category):
                raise ValueError("latest-subscription category exceeds protocol limit")
            if any(protocol_for_uri(uri) != category for uri in lines):
                raise ValueError("latest-subscription category contains invalid URI")
        identities = [_identity(uri) for uri in lines]
        if len(identities) != len(set(identities)):
            raise ValueError("latest-subscription duplicate semantic identity")
        if category == "all":
            if set(lines) != all_uris:
                raise ValueError("latest-subscription aggregate is not the protocol union")
        else:
            if set(lines) & all_uris:
                raise ValueError("latest-subscription duplicate URI across categories")
            all_uris.update(lines)
    if {item.name for item in directory.iterdir()} != expected_files:
        raise ValueError("latest-subscription directory has unexpected or missing files")
    return index
