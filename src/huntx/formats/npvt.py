import base64
import binascii
import json
import re
from typing import List, Dict, Any
from .base import FormatHandler
from .common.normalize_text import normalize_text
from .common.hashing import hash_string
from .proxy_uri_validator import validate_proxy_uri

from ..core.router import _PROXY_SCHEMES

_PROXY_URI_RE = re.compile(
    r"(?:" + "|".join(re.escape(s) for s in _PROXY_SCHEMES) + r')[^\s<>"\']+',
    re.IGNORECASE,
)


def _is_proxy_line(line: str) -> bool:
    return any(line.startswith(s) for s in _PROXY_SCHEMES)


def _extract_proxy_uris(text: str) -> List[str]:
    return _PROXY_URI_RE.findall(text)


def _b64_decode_safe(data: str) -> str:
    normalized = data.replace("-", "+").replace("_", "/")
    normalized += "=" * ((4 - len(normalized) % 4) % 4)
    decoded = base64.b64decode(normalized, validate=True)
    return decoded.decode("utf-8")


def strip_proxy_remark(uri: str) -> str:
    if uri.startswith("vmess://"):
        try:
            b64 = uri[8:]
            raw = _b64_decode_safe(b64)
            obj = json.loads(raw)
            obj.pop("ps", None)
            canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
            return "vmess://" + base64.b64encode(canonical.encode()).decode()
        except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return uri
    idx = uri.rfind("#")
    if idx > 0:
        return uri[:idx]
    return uri


def add_clean_remark(uri: str, counter: dict) -> str:
    scheme = uri.split("://")[0].lower() if "://" in uri else "proxy"
    counter[scheme] = counter.get(scheme, 0) + 1
    tag = f"{scheme}-{counter[scheme]}"

    if uri.startswith("vmess://"):
        try:
            b64 = uri[8:]
            raw = _b64_decode_safe(b64)
            obj = json.loads(raw)
            obj["ps"] = tag
            encoded = json.dumps(obj, separators=(",", ":")).encode()
            return "vmess://" + base64.b64encode(encoded).decode()
        except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return uri

    idx = uri.rfind("#")
    base = uri[:idx] if idx > 0 else uri
    return f"{base}#{tag}"


class NpvtHandler(FormatHandler):
    """Parse validated proxy URI records and build deterministic subscriptions."""

    @property
    def format_id(self) -> str:
        return "npvt"

    def _append_uri(
        self,
        records: List[Dict[str, Any]],
        seen_hashes: set[str],
        candidate: str,
    ) -> None:
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
        records.append({"unique_hash": digest, "data": {"line": stripped}})

    def parse(self, raw_data: bytes, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            text = raw_data.decode("utf-8")
        except UnicodeDecodeError:
            return []

        clean_text = text.strip()
        if "://" not in clean_text and " " not in clean_text and len(clean_text) > 10:
            try:
                decoded = _b64_decode_safe(clean_text)
                if any(s in decoded for s in _PROXY_SCHEMES):
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
        lines = []
        seen = set()
        remark_counter: dict = {}
        for record in records:
            line = None
            if isinstance(record, dict):
                if "data" in record and isinstance(record["data"], dict):
                    line = record["data"].get("line")
                elif "line" in record:
                    line = record["line"]
            if not isinstance(line, str) or not validate_proxy_uri(line):
                continue
            stripped = strip_proxy_remark(line)
            if stripped not in seen:
                seen.add(stripped)
                lines.append(add_clean_remark(stripped, remark_counter))
        return "\n".join(lines).encode("utf-8")
