from typing import List, Dict, Any
from .base import FormatHandler
from .common.normalize_text import normalize_text
from .common.hashing import hash_string
import base64

class NpvtHandler(FormatHandler):
    """
    Handles proxy configs like vmess://, vless://, trojan:// etc.
    Sometimes these are base64 encoded.
    """
    @property
    def format_id(self) -> str:
        return "npvt"

    def parse(self, raw_data: bytes, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = raw_data.decode("utf-8", errors="ignore")

        # Try to decode if it looks like base64 (no spaces, length multiple of 4 roughly)
        clean_text = text.strip()
        if "://" not in clean_text and not " " in clean_text:
            try:
                decoded = base64.b64decode(clean_text).decode("utf-8", errors="ignore")
                text = decoded
            except Exception:
                pass # Not base64 or failed

        records = []
        for line in text.splitlines():
            clean = normalize_text(line)
            if not clean:
                continue

            # Simple heuristic: must contain :// or be a known format
            # For strictness we could check schemas
            if "://" in clean or "ssr://" in clean:
                record = {
                    "unique_hash": hash_string(clean),
                    "data": {"line": clean}
                }
                records.append(record)
        return records

    def build(self, records: List[Dict[str, Any]]) -> bytes:
        # Similar to conf_lines, join unique lines
        lines = []
        seen = set()
        for r in records:
            line = r["data"]["line"]
            if line not in seen:
                lines.append(line)
                seen.add(line)

        # Often these are distributed as base64 of the list
        content = "\n".join(lines)
        return content.encode("utf-8")
        # Note: Some clients expect base64 encoded list.
        # But for 'npvt' usually we return the text list or base64.
        # Let's stick to plain text list for now as it's more universal for 'merge'.
