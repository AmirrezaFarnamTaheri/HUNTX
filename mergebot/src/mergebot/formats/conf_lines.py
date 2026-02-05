from typing import List, Dict, Any
from .base import FormatHandler
from .common.normalize_text import normalize_text
from .common.hashing import hash_string

class ConfLinesHandler(FormatHandler):
    @property
    def format_id(self) -> str:
        return "conf_lines"

    def parse(self, raw_data: bytes, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = raw_data.decode("utf-8", errors="ignore")
        records = []
        for line in text.splitlines():
            clean = normalize_text(line)
            if not clean or clean.startswith("#"):
                continue

            # Record structure
            record = {
                "unique_hash": hash_string(clean),
                "data": {"line": clean}
            }
            records.append(record)
        return records

    def build(self, records: List[Dict[str, Any]]) -> bytes:
        lines = []
        seen = set()
        for r in records:
            line = r["data"]["line"]
            if line not in seen:
                lines.append(line)
                seen.add(line)
        return "\n".join(lines).encode("utf-8")
