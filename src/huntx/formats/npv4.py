import logging
from typing import Any, Dict, List, Optional

from ..store.raw_store import RawStore
from .common.crypto import MissingSecretError, decrypt_tut_data
from .common.hashing import hash_bytes
from .opaque_bundle import OpaqueBundleHandler

logger = logging.getLogger(__name__)


class Npv4Handler(OpaqueBundleHandler):
    """NapsternetV v4 blobs with optional decryption metadata enrichment."""

    def __init__(self, raw_store: RawStore):
        super().__init__(raw_store, "npv4")

    def parse(
        self,
        raw_data: bytes,
        source_info: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        source_info = source_info or {}
        raw_hash = hash_bytes(raw_data)
        data: Dict[str, Any] = {
            "filename": source_info.get("filename", f"{raw_hash}.npv4"),
            "blob_hash": raw_hash,
            "size": len(raw_data),
        }

        try:
            text = raw_data.decode("utf-8", "ignore")
            if "." in text and len(text) > 50:
                decrypted = decrypt_tut_data(text, extension=".sks")
                if decrypted:
                    data["content"] = text
                    data["decrypted"] = decrypted
        except MissingSecretError:
            logger.debug(
                "NPV4 decryption credential is not configured; preserving opaque blob"
            )
        except Exception as exc:
            logger.debug("NPV4 deep parsing failed: %s", exc)

        return [
            {
                "type": self.format_id,
                "unique_hash": raw_hash,
                "data": data,
            }
        ]
