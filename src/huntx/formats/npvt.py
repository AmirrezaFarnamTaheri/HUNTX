import re
from typing import List, Dict, Any
from .base import FormatHandler
from .common.normalize_text import normalize_text
from .common.hashing import hash_string
import base64

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
                h = hash_string(clean)
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    records.append({"unique_hash": h, "data": {"line": clean}})
                continue

            # Slow path: extract URIs embedded mid-line
            # (e.g., "🔴 New config vmess://abc..." or "Use: vless://xyz...")
            uris = _extract_proxy_uris(clean)
            for uri in uris:
                uri = uri.strip()
                h = hash_string(uri)
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    records.append({"unique_hash": h, "data": {"line": uri}})

        return records

    def build(self, records: List[Dict[str, Any]]) -> bytes:
        lines = []
        seen = set()
        for r in records:
            line = None
            if isinstance(r, dict):
                if "data" in r and isinstance(r["data"], dict) and "line" in r["data"]:
                    line = r["data"]["line"]
                elif "line" in r:
                    line = r["line"]

            if line and line not in seen:
                lines.append(line)
                seen.add(line)

        content = "\n".join(lines)
        return content.encode("utf-8")
