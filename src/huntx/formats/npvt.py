import base64
import binascii
import json
import math
import os
import re
import time
from urllib.parse import quote, unquote
from typing import Any, Dict, List

from .base import FormatHandler
from .common.b64 import b64_decode as _b64_decode_safe
from .common.hashing import hash_string
from .common.normalize_text import normalize_text
from .proxy_uri_validator import validate_proxy_uri
from ..core.router import _AUTH_HTTP_PROXY_RE, _PROXY_SCHEMES

_REPORT_PROXY_SCHEMES = _PROXY_SCHEMES + ('http://', 'https://')
_PROXY_URI_RE = re.compile(
    '(?:' + '|'.join((re.escape(s) for s in _PROXY_SCHEMES)) + ')[^\\s<>"\\\']+',
    re.IGNORECASE,
)


def _is_proxy_line(line: str) -> bool:
    """Return whether a complete line is a supported proxy URI."""
    if any(line.startswith(s) for s in _PROXY_SCHEMES):
        return True
    return line.lower().startswith(('http://', 'https://')) and validate_proxy_uri(line)


def _extract_proxy_uris(text: str) -> List[str]:
    """Extract supported proxy URIs embedded in arbitrary text."""
    matches = _PROXY_URI_RE.findall(text)
    matches.extend(match.group(0) for match in _AUTH_HTTP_PROXY_RE.finditer(text))
    return matches


# Transports worth naming in a remark. "raw"/"" carry no information, and
# naming them would just add noise to every second node.
_REMARK_TRANSPORTS = frozenset({
    'ws', 'websocket', 'grpc', 'http', 'h2', 'xhttp', 'httpupgrade',
    'quic', 'kcp', 'splithttp',
})

# Protocols whose transport is TLS by design. Naming "tls" on them would put the
# same word on every node of that type, which tells a reader nothing.
_TLS_IMPLYING_SCHEMES = frozenset({
    'trojan', 'hysteria', 'hysteria2', 'hy2', 'anytls', 'tuic', 'ssr',
})


def remark_qualifier(uri: str) -> str:
    """Return the transport/security qualifier for one node's remark.

    Deterministic and derived from the URI alone, so the same node always
    produces the same remark. Returns an empty string when the node has no
    distinguishing transport or security, which keeps a plain TCP VLESS node
    reading ``vless-3`` rather than ``vless-tcp-none-3``.
    """
    try:
        from .common.singbox import parse_proxy_uri

        node = parse_proxy_uri(uri)
    except Exception:
        return ''
    if node is None:
        return ''
    parts: list[str] = []
    transport = (node.transport_type or '').strip().lower()
    if transport in _REMARK_TRANSPORTS:
        parts.append('ws' if transport == 'websocket' else transport)
    scheme = (node.type or '').lower()
    if node.tls_reality_enabled:
        parts.append('reality')
    elif node.tls_enabled and scheme not in _TLS_IMPLYING_SCHEMES:
        parts.append('tls')
    return '-'.join(parts)


def strip_proxy_remark(uri: str) -> str:
    """Remove display remarks while preserving proxy semantics."""
    if uri.startswith('vmess://'):
        try:
            body = uri.partition('#')[0]
            b64 = body[8:]
            raw = _b64_decode_safe(b64)
            obj = json.loads(raw)
            obj.pop('ps', None)
            canonical = json.dumps(obj, sort_keys=True, separators=(',', ':'))
            return 'vmess://' + base64.b64encode(canonical.encode()).decode()
        except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return uri
    idx = uri.rfind('#')
    if idx > 0:
        return uri[:idx]
    return uri


def _country_to_flag(code: str) -> str:
    """Convert ISO 2-letter country code to emoji flag."""
    code = code.upper().strip()
    if len(code) != 2 or not code.isascii() or not code.isalpha() or code == "ZZ":
        return "🌐"
    return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)


def _detect_operator(uri: str) -> str:
    """Infer operator or CDN name from URI string."""
    low = uri.lower()
    if uri.startswith('vmess://'):
        try:
            b64 = uri[8:]
            decoded_text = _b64_decode_safe(b64).lower()
            low = f"{low} {decoded_text}"
        except Exception:
            pass
    if any(k in low for k in ("mci", "mcci", "hamrah")):
        return "MCI"
    if any(k in low for k in ("mtn", "irancell")):
        return "MTN"
    if any(k in low for k in ("rtl", "rightel")):
        return "RTL"
    if any(k in low for k in ("cloudflare", "cf-", "workers.dev", "pages.dev")):
        return "CF"
    if any(k in low for k in ("hetzner", "your-server.de")):
        return "Hetzner"
    if any(k in low for k in ("digitalocean", "do-")):
        return "DO"
    if "ovh" in low:
        return "OVH"
    if "arvan" in low:
        return "Arvan"
    return ""


def format_enriched_remark(uri: str, counter: dict, metadata: dict | None = None) -> str:
    """Format an information-dense display remark with geo, protocol, and stats.

    Not wired to the published feed. Every production call site of
    ``add_clean_remark`` passes no metadata, so the published artifacts carry the
    clean ``{scheme}-{n}`` tag. The dashboard displays that exact string, so a
    node reads the same in a client as it does on the site. Adopting this form
    for the feed would change what subscribers see and break that parity; it is
    available for a surface that wants geo and grade in the remark itself.
    """
    scheme = uri.split('://')[0].lower() if '://' in uri else 'proxy'
    counter[scheme] = counter.get(scheme, 0) + 1
    idx = counter[scheme]

    if not metadata:
        tag = f'{scheme}-{idx}'
    else:
        raw_country = metadata.get('country')
        country = raw_country.strip().upper() if isinstance(raw_country, str) else 'ZZ'
        if len(country) != 2 or not country.isascii() or not country.isalpha():
            country = 'ZZ'
        flag = _country_to_flag(country)
        # An upstream remark/secret is not operator evidence. Display only
        # an explicitly verified operator label, never one guessed from URI text.
        operator = metadata.get('operator')
        op = operator.strip()[:24] if (
            isinstance(operator, str) and metadata.get('operator_verified') is True
            and operator.strip().isascii()
            and operator.strip().replace('-', '').isalnum()
        ) else ''
        op_tag = f"-{op}" if op else ""
        # Protocol tag carries the transport and security actually in use so
        # a user picking a node from a long list can tell a plain TCP VLESS
        # from a REALITY-over-gRPC one at a glance.
        proto_tag = scheme.upper()
        transport = metadata.get('transport') or metadata.get('network') or ''
        security = metadata.get('security') or ''
        for detail in (transport, security):
            if isinstance(detail, str) and detail.strip().lower() not in ('', 'none', 'auto', 'unknown'):
                proto_tag += '-' + detail.strip().upper()

        parts = [f"{flag} {country}{op_tag}", proto_tag]

        latency = metadata.get('latency_ms')
        if (
            isinstance(latency, (int, float))
            and not isinstance(latency, bool)
            and latency >= 0
            and math.isfinite(latency)
        ):
            parts.append(f"⚡{latency}ms")
        # A measured probe result outranks a caller-declared grade: an
        # unreachable node advertises its failure instead of a score.
        grade = metadata.get('health_grade')
        probe_failed = metadata.get('probe_ok') is False
        authenticated = (
            metadata.get('probe_kind') == 'protocol_authenticated'
            and metadata.get('probe_ok') is True
            and isinstance(metadata.get('probe_age_seconds'), (int, float))
            and not isinstance(metadata.get('probe_age_seconds'), bool)
            and math.isfinite(metadata['probe_age_seconds'])
            and 0 <= metadata['probe_age_seconds'] <= 3600
        )
        if probe_failed:
            parts.append("⭐F")
        elif authenticated and isinstance(grade, str) and grade.strip() in {
            'A+', 'A', 'B', 'C', 'D', 'F'
        }:
            parts.append(f"⭐{grade.strip()}")
        parts.append(f"#{idx:03d}")
        tag = " | ".join(parts)

    return tag



# ISO hints are deliberately separate from independently sourced IP evidence.
_HINT_COUNTRIES = frozenset({
    'US', 'DE', 'FR', 'GB', 'NL', 'SG', 'JP', 'CA', 'AU', 'IR', 'KR', 'CN',
    'RU', 'HK', 'TW', 'SE', 'FI', 'CH', 'IT', 'ES', 'TR', 'IN', 'BR', 'PL',
    'RO', 'UA', 'AE', 'ZA', 'NO', 'DK', 'BE', 'AT', 'CZ', 'GR', 'PT', 'IE',
})


def _remark_country_hint(uri: str) -> str | None:
    """Only consume an explicitly tagged country from the untrusted fragment."""
    fragment = uri.split('#', 1)[1] if '#' in uri else ''
    if not fragment or len(fragment) > 256:
        return None
    readable = unquote(fragment).upper()
    for match in re.finditer(r'(?<![A-Z])([A-Z]{2})(?![A-Z])', readable):
        code = match.group(1)
        if code in _HINT_COUNTRIES:
            return code
    return None


def format_evidence_remark(uri: str, metadata: dict | None = None) -> str:
    """Create a short, stable, evidence-labeled client tag.

    Flags without '?' require an unexpired authoritative prefix attribution.
    Source-provided country fragments are hints only and carry '?'. A TCP
    connect cannot promote an endpoint to a healthy authenticated proxy.
    """
    fields = metadata if isinstance(metadata, dict) else {}
    endpoint = fields.get('endpoint')
    endpoint = endpoint if isinstance(endpoint, dict) else {}
    intel = endpoint.get('intelligence')
    intel = intel if isinstance(intel, dict) else {}
    geo = endpoint.get('geo')
    geo = geo if isinstance(geo, dict) else {}
    expiration = intel.get('expires_at')
    fresh = (
        intel.get('status') == 'matched'
        and type(expiration) in (float, int)
        and math.isfinite(expiration) and expiration > time.time()
    )
    country = geo.get('country_code')
    proven = (
        fresh and geo.get('status') == 'prefix_dataset_estimate'
        and isinstance(country, str) and country in _HINT_COUNTRIES
    )
    if proven:
        location = f'{_country_to_flag(country)} {country}'
    else:
        hint = fields.get('country_hint')
        if (
            isinstance(hint, str) and hint in _HINT_COUNTRIES
            and fields.get('country_hint_source') == 'source_remark'
        ):
            location = f'{_country_to_flag(hint)}? {hint}'
        else:
            location = '🌐 ZZ'

    scheme = uri.split('://', 1)[0].upper() if '://' in uri else 'PROXY'
    label = re.sub(r'[^A-Z0-9+_-]', '', scheme)[:18] or 'PROXY'
    qualifier = remark_qualifier(uri).upper()
    if qualifier:
        label += '-' + qualifier[:24]

    details: list[str] = []
    asn = endpoint.get('asn')
    if fresh and type(asn) is int and 0 < asn <= 4294967295:
        details.append(f'AS{asn}')
        cdn = endpoint.get('cdn_provider')
        if isinstance(cdn, str):
            cleaned = re.sub(r'[^a-zA-Z0-9 -]', '', cdn).strip()[:15]
            if cleaned:
                details.append('CDN:' + cleaned.replace(' ', '-'))

    now = time.time()
    elapsed = fields.get('latency_ms')
    observed = fields.get('probe_checked_at')
    expires = fields.get('probe_expires_at')
    fresh_probe = (
        type(elapsed) in (int, float) and math.isfinite(elapsed)
        and 0 <= elapsed <= 60000
        and type(observed) in (int, float) and math.isfinite(observed)
        and type(expires) in (int, float) and math.isfinite(expires)
        and observed <= now < expires
    )
    if fresh_probe:
        if fields.get('probe_kind') == 'tcp_connect':
            details.append(f'TCP:{round(elapsed)}ms')
        elif (
            fields.get('probe_kind') == 'protocol_authenticated'
            and fields.get('probe_authenticated') is True
        ):
            details.append(f'AUTH:{round(elapsed)}ms')

    # Stable within credential identity, independent of sorting and source order.
    identifier = hash_string(strip_proxy_remark(uri))[:10]
    parts = [location, label, *details, identifier]
    return ' | '.join(parts)[:110]


def add_clean_remark(uri: str, counter: dict, metadata: dict | None = None) -> str:
    """Attach a deterministic display remark to a proxy URI.

    Legacy ordinal tags remain the default for client compatibility. Enabling
    HUNTX_REMARK_STYLE=stable replaces the ordinal with a 48-bit canonical URI
    digest, avoiding name churn when sources reorder. Neither mode invents
    country, speed, or health status.
    """
    evidence_style = os.getenv("HUNTX_REMARK_STYLE", "legacy").lower() == "evidence"
    if evidence_style:
        tag = format_evidence_remark(uri, metadata)
    elif metadata:
        tag = format_enriched_remark(uri, counter, metadata)
    else:
        scheme = uri.split('://')[0].lower() if '://' in uri else 'proxy'
        qualifier = remark_qualifier(uri)
        # Preserve established client tags by default. Operators may opt into
        # deterministic identities (HUNTX_REMARK_STYLE=stable) when migrating
        # subscribers; never attach unverified geo/latency marketing labels.
        if os.getenv("HUNTX_REMARK_STYLE", "legacy").lower() == "stable":
            identity = hash_string(strip_proxy_remark(uri))[:12]
        else:
            counter[scheme] = counter.get(scheme, 0) + 1
            identity = str(counter[scheme])
        tag = f'{scheme}-{qualifier}-{identity}' if qualifier else f'{scheme}-{identity}'

    if uri.startswith('vmess://'):
        try:
            body = uri.partition("#")[0]
            b64 = body[8:]
            raw = _b64_decode_safe(b64)
            obj = json.loads(raw)
            obj['ps'] = tag
            encoded = json.dumps(obj, separators=(',', ':')).encode()
            return 'vmess://' + base64.b64encode(encoded).decode()
        except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return uri
    idx = uri.rfind('#')
    base = uri[:idx] if idx > 0 else uri
    return f'{base}#{quote(tag, safe="-._~") if evidence_style else tag}'


class NpvtHandler(FormatHandler):
    """Parse validated proxy URI records and build deterministic subscriptions."""

    @property
    def format_id(self) -> str:
        """Return the format identifier."""
        return 'npvt'

    def _append_uri(
        self,
        records: List[Dict[str, Any]],
        seen_hashes: set[str],
        candidate: str,
    ) -> None:
        """Validate, deduplicate, and append one proxy URI record."""
        uri = candidate.strip()
        if not validate_proxy_uri(uri):
            return
        stripped = strip_proxy_remark(uri)
        if not validate_proxy_uri(stripped):
            return
        digest = hash_string(stripped)
        if digest in seen_hashes:
            return
        seen_hashes.add(digest)
        payload = {'line': stripped}
        if os.getenv("HUNTX_REMARK_STYLE", "legacy").lower() == "evidence":
            hint = _remark_country_hint(uri)
            if hint:
                payload['country_hint'] = hint
                payload['country_hint_source'] = 'source_remark'
        records.append({'unique_hash': digest, 'data': payload})

    def parse(
        self,
        raw_data: bytes,
        source_info: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Parse proxy text into validated deduplicated records."""
        try:
            text = raw_data.decode('utf-8')
        except UnicodeDecodeError:
            return []
        clean_text = text.strip()
        if '://' not in clean_text and ' ' not in clean_text and len(clean_text) > 10:
            try:
                decoded = _b64_decode_safe(clean_text)
                if any(s in decoded for s in _PROXY_SCHEMES) or _AUTH_HTTP_PROXY_RE.search(decoded):
                    text = decoded
            except (binascii.Error, UnicodeDecodeError, ValueError):
                pass
        records: List[Dict[str, Any]] = []
        seen_hashes: set[str] = set()
        for line in text.splitlines():
            clean = normalize_text(line)
            if not clean:
                continue
            if _is_proxy_line(clean):
                self._append_uri(records, seen_hashes, clean)
                continue
            for uri in _extract_proxy_uris(clean):
                self._append_uri(records, seen_hashes, uri)
        return records

    def build(self, records: List[Dict[str, Any]]) -> bytes:
        """Build a deterministic newline-delimited proxy subscription."""
        lines = []
        seen = set()
        remark_counter: dict = {}
        for record in records:
            line = None
            evidence_metadata = None
            if isinstance(record, dict):
                if 'data' in record and isinstance(record['data'], dict):
                    line = record['data'].get('line')
                    if os.getenv("HUNTX_REMARK_STYLE", "legacy").lower() == "evidence":
                        evidence_metadata = record['data']
                elif 'line' in record:
                    line = record['line']
            if not isinstance(line, str) or not validate_proxy_uri(line):
                continue
            stripped = strip_proxy_remark(line)
            if stripped not in seen:
                seen.add(stripped)
                lines.append(add_clean_remark(stripped, remark_counter, evidence_metadata))
        return '\n'.join(lines).encode('utf-8')
