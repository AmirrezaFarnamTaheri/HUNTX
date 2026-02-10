import base64
import json
import re
from typing import List, Dict, Any
from .base import FormatHandler
from .common.normalize_text import normalize_text
from .common.hashing import hash_string

# All known proxy URI schemes
_PROXY_SCHEMES = (
    "vmess://", "vless://", "trojan://",
    "ss://", "ssr://",
    "hysteria2://", "hy2://", "hysteria://",
    "tuic://",
    "wireguard://", "wg://",
    "socks://", "socks5://", "socks4://",
    "anytls://",
    "juicity://",
    "warp://",
    "dns://", "dnstt://",
)

# Regex to extract proxy URIs from anywhere in text.
# Matches scheme:// followed by non-whitespace characters.
_PROXY_URI_RE = re.compile(
    r'(?:' + '|'.join(re.escape(s) for s in _PROXY_SCHEMES) + r')[^\s<>\"\']+',
    re.IGNORECASE,
)


def _is_proxy_line(line: str) -> bool:
    """Check if a line starts with a known proxy URI scheme."""
    return any(line.startswith(s) for s in _PROXY_SCHEMES)


def _extract_proxy_uris(text: str) -> List[str]:
    """Extract all proxy URIs from text, even if embedded mid-line."""
    return _PROXY_URI_RE.findall(text)


def _b64_decode_safe(data: str) -> str:
    """Base64 decode with auto-padding, supports URL-safe variant."""
    data = data.replace("-", "+").replace("_", "/")
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.b64decode(data).decode("utf-8", errors="ignore")


def strip_proxy_remark(uri: str) -> str:
    """Strip the remark/tag from a proxy URI for deduplication.

    For vmess:// — decode base64 JSON, remove 'ps' field, re-encode
    deterministically so identical proxies with different remarks hash the same.
    For all others — strip the #fragment.
    """
    if uri.startswith("vmess://"):
        try:
            b64 = uri[8:]
            raw = _b64_decode_safe(b64)
            obj = json.loads(raw)
            obj.pop("ps", None)
            canonical = json.dumps(obj, sort_keys=True, separators=(',', ':'))
            return "vmess://" + base64.b64encode(canonical.encode()).decode()
        except Exception:
            pass
    # For all other protocols: strip #fragment
    idx = uri.rfind("#")
    if idx > 0:
        return uri[:idx]
    return uri


def add_clean_remark(uri: str, counter: dict) -> str:
    """Replace any existing remark with a clean protocol-N tag.

    For vmess:// — set 'ps' field in decoded JSON.
    For all others — append #protocol-N.
    """
    scheme = uri.split("://")[0].lower() if "://" in uri else "proxy"
    counter[scheme] = counter.get(scheme, 0) + 1
    tag = f"{scheme}-{counter[scheme]}"

    if uri.startswith("vmess://"):
        try:
            b64 = uri[8:]
            raw = _b64_decode_safe(b64)
            obj = json.loads(raw)
            obj["ps"] = tag
            encoded = json.dumps(obj, separators=(',', ':')).encode()
            return "vmess://" + base64.b64encode(encoded).decode()
        except Exception:
            return uri

    # Strip existing fragment, add clean one
    idx = uri.rfind("#")
    base = uri[:idx] if idx > 0 else uri
    return f"{base}#{tag}"


class NpvtHandler(FormatHandler):
    """
    Handles proxy configs like vmess://, vless://, trojan://, ss://, ssr://,
    hysteria2://, tuic://, wireguard://, socks://, dns://, juicity://, etc.
    Input may be plain text lines or a base64-encoded blob.
    """

    @property
    def format_id(self) -> str:
        return "npvt"

    def parse(self, raw_data: bytes, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = raw_data.decode("utf-8", errors="ignore")

        # Try to decode if it looks like base64 (no spaces, no ://)
        clean_text = text.strip()
        if "://" not in clean_text and " " not in clean_text and len(clean_text) > 10:
            try:
                padding = 4 - len(clean_text) % 4
                if padding != 4:
                    clean_text += "=" * padding
                decoded = base64.b64decode(clean_text).decode("utf-8", errors="ignore")
                if any(s in decoded for s in _PROXY_SCHEMES):
                    text = decoded
            except Exception:
                pass  # Not base64 or failed

        records = []
        seen_hashes = set()

        for line in text.splitlines():
            clean = normalize_text(line)
            if not clean:
                continue

            # Fast path: line starts with a proxy scheme (most common case)
            if _is_proxy_line(clean):
                stripped = strip_proxy_remark(clean)
                h = hash_string(stripped)
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    records.append({"unique_hash": h, "data": {"line": stripped}})
                continue

            # Slow path: extract URIs embedded mid-line
            uris = _extract_proxy_uris(clean)
            for uri in uris:
                uri = uri.strip()
                stripped = strip_proxy_remark(uri)
                h = hash_string(stripped)
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    records.append({"unique_hash": h, "data": {"line": stripped}})

        return records

    def build(self, records: List[Dict[str, Any]]) -> bytes:
        lines = []
        seen = set()
        remark_counter: dict = {}
        for r in records:
            line = None
            if isinstance(r, dict):
                if "data" in r and isinstance(r["data"], dict) and "line" in r["data"]:
                    line = r["data"]["line"]
                elif "line" in r:
                    line = r["line"]

            if not line:
                continue
            stripped = strip_proxy_remark(line)
            if stripped not in seen:
                seen.add(stripped)
                lines.append(add_clean_remark(stripped, remark_counter))

        content = "\n".join(lines)
        return content.encode("utf-8")
