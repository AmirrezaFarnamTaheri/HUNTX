import logging
import os
import zipfile
import io
from typing import List, Dict, Any
from .base import FormatHandler
from .common.hashing import hash_bytes
from ..store.raw_store import RawStore
from ..utils.safe_names import safe_zip_entry_name

logger = logging.getLogger(__name__)

# Bounded-resource ceilings for bundle assembly. ``build`` reads blobs into a
# single in-memory ZIP; without a ceiling a route referencing many/large blobs
# can drive an unbounded allocation (OOM). Defaults are generous enough that
# normal operation never trips them, and any truncation is logged explicitly
# rather than dropped silently. Both are overridable via environment.
_DEFAULT_MAX_BYTES = 1024 * 1024 * 1024  # 1 GiB of uncompressed source content
_DEFAULT_MAX_ENTRIES = 100_000


def _int_env(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back on default."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r; using default %d", name, raw, default)
        return default
    return value if value > 0 else default


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
        # Create a ZIP file containing all records, bounded by explicit
        # resource ceilings so a pathological record set cannot exhaust memory.
        max_bytes = _int_env("HUNTX_OPAQUE_BUNDLE_MAX_BYTES", _DEFAULT_MAX_BYTES)
        max_entries = _int_env("HUNTX_OPAQUE_BUNDLE_MAX_ENTRIES", _DEFAULT_MAX_ENTRIES)

        buffer = io.BytesIO()
        seen_names: set = set()
        total_bytes = 0
        entries = 0
        dropped = 0

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for r in records:
                data = r.get("data", {})
                blob_hash = data.get("blob_hash")
                if not blob_hash:
                    continue
                original_name = data.get("filename", "file.bin")

                # Retrieve content
                content = self.raw_store.get(blob_hash)
                if not content:
                    logger.warning(
                        f"[{self._format_name}] Raw blob missing for {original_name} "
                        f"(hash={blob_hash[:12]}), skipping."
                    )
                    continue

                # Enforce bounded-resource ceilings before allocating the entry.
                if entries >= max_entries or total_bytes + len(content) > max_bytes:
                    dropped += 1
                    continue

                # Handle name collisions
                name = safe_zip_entry_name(original_name, default="file.bin")
                counter = 1
                while name in seen_names:
                    name = f"{counter}_{safe_zip_entry_name(original_name, default='file.bin')}"
                    counter += 1
                seen_names.add(name)

                zf.writestr(name, content)
                total_bytes += len(content)
                entries += 1

        if dropped:
            logger.warning(
                "[%s] Bundle ceiling reached (max_bytes=%d, max_entries=%d): "
                "included %d entries (%d bytes), dropped %d record(s). "
                "Raise HUNTX_OPAQUE_BUNDLE_MAX_BYTES/MAX_ENTRIES to include more.",
                self._format_name, max_bytes, max_entries, entries, total_bytes, dropped,
            )

        return buffer.getvalue()
