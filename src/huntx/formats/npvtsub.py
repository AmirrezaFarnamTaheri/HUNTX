from typing import List, Dict, Any
import binascii
from .base import FormatHandler
from .common.normalize_text import normalize_text
from .common.hashing import hash_string
from .npvt import _PROXY_SCHEMES, _is_proxy_line, _extract_proxy_uris, strip_proxy_remark, add_clean_remark
import base64


class NpvtSubHandler(FormatHandler):
    """
    Handles .npvtsub subscription files containing proxy URIs.
    Supports all proxy protocols: vmess, vless, trojan, ss, ssr,
    hysteria2, tuic, wireguard, socks, dns, juicity, anytls, warp, etc.
    Input is typically plain-text or base64-encoded list of proxy URIs.
    """

    @property
    def format_id(self) -> str:
        return "npvtsub"

    def parse(self, raw_data: bytes, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = raw_data.decode("utf-8", errors="ignore")

        # Try base64 decode if it doesn't look like plain URIs
        clean_text = text.strip()
        if "://" not in clean_text and " " not in clean_text and len(clean_text) > 10:
            try:
                padding = 4 - len(clean_text) % 4
                if padding != 4:
                    clean_text += "=" * padding
                decoded = base64.b64decode(clean_text).decode("utf-8", errors="ignore")
                if any(s in decoded for s in _PROXY_SCHEMES):
                    text = decoded
            except (binascii.Error, ValueError):
                pass

        records = []
        seen_hashes = set()

        for line in text.splitlines():
            clean = normalize_text(line)
            if not clean:
                continue

            # Fast path: line starts with a proxy scheme
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
        seen: set = set()
        remark_counter: dict = {}
        for r in records:
            line = None
            if isinstance(r, dict):
                data = r.get("data")
                if isinstance(data, dict):
                    line = data.get("line")
                elif isinstance(r.get("line"), str):
                    line = r["line"]
            if not line:
                continue
            stripped = strip_proxy_remark(line)
            if stripped not in seen:
                seen.add(stripped)
                lines.append(add_clean_remark(stripped, remark_counter))
        content = "\n".join(lines)
        return content.encode("utf-8")
