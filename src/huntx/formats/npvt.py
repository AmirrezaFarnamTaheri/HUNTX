import base64
import binascii
import json
import re
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


def strip_proxy_remark(uri: str) -> str:
    """Remove display remarks while preserving proxy semantics."""
    if uri.startswith('vmess://'):
        try:
            b64 = uri[8:]
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
    if len(code) != 2 or not code.isalpha():
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
    """Format an information-dense display remark with geo, protocol, and stats."""
    scheme = uri.split('://')[0].lower() if '://' in uri else 'proxy'
    counter[scheme] = counter.get(scheme, 0) + 1
    idx = counter[scheme]

    if not metadata:
        tag = f'{scheme}-{idx}'
    else:
        country = metadata.get('country', 'DE').upper()
        flag = _country_to_flag(country)
        op = metadata.get('operator') or _detect_operator(uri)
        op_tag = f"-{op}" if op else ""
        proto_tag = scheme.upper()
        
        parts = [f"{flag} {country}{op_tag}", proto_tag]
        
        if 'latency_ms' in metadata:
            parts.append(f"⚡{metadata['latency_ms']}ms")
        if 'health_grade' in metadata:
            parts.append(f"⭐{metadata['health_grade']}")
        parts.append(f"#{idx:03d}")
        tag = " | ".join(parts)

    return tag


def add_clean_remark(uri: str, counter: dict, metadata: dict | None = None) -> str:
    """Attach a deterministic display remark to a proxy URI."""
    if metadata:
        tag = format_enriched_remark(uri, counter, metadata)
    else:
        scheme = uri.split('://')[0].lower() if '://' in uri else 'proxy'
        counter[scheme] = counter.get(scheme, 0) + 1
        tag = f'{scheme}-{counter[scheme]}'

    if uri.startswith('vmess://'):
        try:
            b64 = uri[8:]
            raw = _b64_decode_safe(b64)
            obj = json.loads(raw)
            obj['ps'] = tag
            encoded = json.dumps(obj, separators=(',', ':')).encode()
            return 'vmess://' + base64.b64encode(encoded).decode()
        except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return uri
    idx = uri.rfind('#')
    base = uri[:idx] if idx > 0 else uri
    return f'{base}#{tag}'


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
        records.append({'unique_hash': digest, 'data': {'line': stripped}})

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
            if isinstance(record, dict):
                if 'data' in record and isinstance(record['data'], dict):
                    line = record['data'].get('line')
                elif 'line' in record:
                    line = record['line']
            if not isinstance(line, str) or not validate_proxy_uri(line):
                continue
            stripped = strip_proxy_remark(line)
            if stripped not in seen:
                seen.add(stripped)
                lines.append(add_clean_remark(stripped, remark_counter))
        return '\n'.join(lines).encode('utf-8')
