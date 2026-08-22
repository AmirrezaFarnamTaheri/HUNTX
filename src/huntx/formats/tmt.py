import logging
from typing import Any, Dict, List, Optional

from ..store.raw_store import RawStore
from .common.crypto import decrypt_tut_data
from .common.hashing import hash_bytes
from .opaque_bundle import OpaqueBundleHandler

logger = logging.getLogger(__name__)


class TmtHandler(OpaqueBundleHandler):
    """Handler for .tmt files with optional deep-decryption metadata."""

    def __init__(self, raw_store: RawStore):
        super().__init__(raw_store, "tmt")

    def parse(
        self,
        raw_data: bytes,
        source_info: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        source_info = source_info or {}
        try:
            text = raw_data.decode("utf-8", "ignore")
            if "." in text and len(text) > 50:
                decrypted = decrypt_tut_data(text, extension=".tmt")
                if decrypted:
                    raw_hash = hash_bytes(raw_data)
                    return [
                        {
                            "type": self.format_id,
                            "unique_hash": raw_hash,
                            "data": {
                                "filename": source_info.get("filename", f"{raw_hash}.tmt"),
                                "blob_hash": raw_hash,
                                "size": len(raw_data),
                                "content": text,
                                "decrypted": decrypted,
                            },
                        }
                    ]
        except Exception as exc:
            logger.debug("TMT deep parsing failed: %s", exc)

        return super().parse(raw_data, source_info)
