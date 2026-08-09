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
        # base sanitized name -> next suffix to try, so collision resolution
        # never rescans from 1 (see the collision block below).
        name_counters: Dict[str, int] = {}
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

                if entries >= max_entries:
                    dropped += 1
                    continue

                # Reject on the record's own declared size *before* reading the
                # blob, so one oversized blob isn't fully loaded into memory
                # only to be dropped afterward. This is a pre-filter, not the
                # authoritative check: the declared size comes from our own
                # parse()-time metadata (trustworthy, but not re-verified
                # against disk), so the post-read len(content) check below
                # remains as the race-safe fallback that actually enforces
                # the ceiling against real bytes.
                declared_size = data.get("size")
                if isinstance(declared_size, int) and total_bytes + declared_size > max_bytes:
                    dropped += 1
                    continue

                # Retrieve content
                content = self.raw_store.get(blob_hash)
                if not content:
                    logger.warning(
                        f"[{self._format_name}] Raw blob missing for {original_name} "
                        f"(hash={blob_hash[:12]}), skipping."
                    )
                    continue

                # Authoritative enforcement against the real bytes read.
                if total_bytes + len(content) > max_bytes:
                    dropped += 1
                    continue

                # Handle name collisions in O(1) per entry.
                #
                # The previous implementation rescanned from counter=1 on every
                # collision AND re-ran safe_zip_entry_name (three regex passes)
                # inside the loop, making this O(n^2) in the number of entries
                # sharing a sanitized name. That is easy to trigger because
                # safe_zip_entry_name collapses everything outside
                # [A-Za-z0-9._-] to "_", so many distinct real-world names
                # (e.g. any all-non-ASCII filename) map to the same token.
                # Measured on the old code: 500 collisions 0.5s, 1500 -> 4.3s,
                # 3000 -> 18s. Since build() holds the per-format lock, that
                # stalls the route entirely. Remembering the next free suffix
                # per base name keeps it linear.
                base_name = safe_zip_entry_name(original_name, default="file.bin")
                name = base_name
                if name in seen_names:
                    counter = name_counters.get(base_name, 1)
                    while name in seen_names:
                        name = f"{counter}_{base_name}"
                        counter += 1
                    name_counters[base_name] = counter
                seen_names.add(name)

                zf.writestr(name, content)
                total_bytes += len(content)
                entries += 1

        if dropped:
            logger.warning(
                "[%s] Bundle ceiling reached (max_bytes=%d, max_entries=%d): "
                "included %d entries (%d bytes), dropped %d record(s). "
                "Raise HUNTX_OPAQUE_BUNDLE_MAX_BYTES/MAX_ENTRIES to include more.",
                self._format_name,
                max_bytes,
                max_entries,
                entries,
                total_bytes,
                dropped,
            )

        return buffer.getvalue()
