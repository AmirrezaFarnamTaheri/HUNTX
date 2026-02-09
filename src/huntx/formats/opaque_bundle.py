import zipfile
import io
from typing import List, Dict, Any
from .base import FormatHandler
from .common.hashing import hash_bytes
from ..store.raw_store import RawStore


class OpaqueBundleHandler(FormatHandler):
    def __init__(self, raw_store: RawStore, format_name: str = "opaque_bundle"):
        self.raw_store = raw_store
        self._format_name = format_name

    @property
    def format_id(self) -> str:
        return self._format_name

    def parse(self, raw_data: bytes, source_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_hash = hash_bytes(raw_data)
        filename = source_info.get("filename", f"{raw_hash}.bin")

        record = {
            "unique_hash": raw_hash,  # Dedup by content
            "data": {"filename": filename, "blob_hash": raw_hash, "size": len(raw_data)},
        }
        return [record]

    def build(self, records: List[Dict[str, Any]]) -> bytes:
        # Create a ZIP file containing all records
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            seen_names = set()
            for r in records:
                data = r.get("data", {})
                blob_hash = data.get("blob_hash")
                if not blob_hash:
                    continue
                original_name = data.get("filename", "file.bin")

                # Retrieve content
                content = self.raw_store.get(blob_hash)
                if not content:
                    continue  # Should warn?

                # Handle name collisions
                name = original_name
                counter = 1
                while name in seen_names:
                    name = f"{counter}_{original_name}"
                    counter += 1
                seen_names.add(name)

                zf.writestr(name, content)

        return buffer.getvalue()
