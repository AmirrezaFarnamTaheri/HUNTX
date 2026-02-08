from typing import List, Dict, Any
from .base import FormatHandler
from .common.normalize_text import normalize_text
from .common.hashing import hash_string
import base64


class NpvtSubHandler(FormatHandler):
    """
    Handles .npvtsub subscription files containing proxy URIs
    (vmess://, vless://, trojan://, ss://, ssr://).
    These are typically plain-text or base64-encoded lists of proxy URIs.
    """

    @property
    def format_id(self) -> str:
        return "npvtsub"

    def parse(self, raw_data: bytes, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = raw_data.decode("utf-8", errors="ignore")

        # Try base64 decode if it doesn't look like plain URIs
        clean_text = text.strip()
        if "://" not in clean_text and " " not in clean_text:
            try:
                decoded = base64.b64decode(clean_text).decode("utf-8", errors="ignore")
                text = decoded
            except Exception:
                pass

        records = []
        for line in text.splitlines():
            clean = normalize_text(line)
            if not clean:
                continue
            if "://" in clean:
                record = {
                    "unique_hash": hash_string(clean),
                    "data": {"line": clean},
                }
                records.append(record)
        return records

    def build(self, records: List[Dict[str, Any]]) -> bytes:
        lines = []
        seen: set = set()
        for r in records:
            line = r["data"]["line"]
            if line not in seen:
                lines.append(line)
                seen.add(line)
        content = "\n".join(lines)
        return content.encode("utf-8")
