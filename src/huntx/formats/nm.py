import logging
from typing import Any, Dict, List, Optional

from .common.crypto import MissingSecretError, decrypt_netmod_data
from .common.hashing import hash_bytes
from .opaque_bundle import OpaqueBundleHandler
from ..store.raw_store import RawStore

logger = logging.getLogger(__name__)


class NmHandler(OpaqueBundleHandler):
    """NetMod encrypted configs with optional deep decryption enrichment.

    The original encrypted file is the canonical record and remains buildable
    even when an operator has not configured the NetMod decryption credential.
    When ``HUNTX_NETMOD_KEY`` is present, a decrypted representation is added as
    metadata; it is never required to preserve or republish the source blob.
    """

    def __init__(self, raw_store: RawStore, format_id: str = "nm"):
        super().__init__(raw_store, format_id)

    def parse(
        self,
        raw_data: bytes,
        source_info: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        source_info = source_info or {}
        raw_hash = hash_bytes(raw_data)
        filename = source_info.get("filename", f"{raw_hash}.nm")
        data: Dict[str, Any] = {
            "filename": filename,
            "blob_hash": raw_hash,
            "size": len(raw_data),
            "content": raw_data.hex(),
        }

        try:
            decrypted = decrypt_netmod_data(raw_data)
        except MissingSecretError:
            logger.debug(
                "NetMod decryption credential is not configured; preserving opaque blob"
            )
            decrypted = None
        except Exception as exc:
            logger.debug("NetMod deep parsing failed: %s", exc)
            decrypted = None

        if decrypted:
            data["decrypted"] = decrypted

        return [
            {
                "type": self.format_id,
                "unique_hash": raw_hash,
                "data": data,
            }
        ]
