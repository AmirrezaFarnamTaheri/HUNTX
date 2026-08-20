import logging
import re
from typing import Any, Dict, List, Optional

from ..store.raw_store import RawStore
from .common.crypto import MissingSecretError, decrypt_happ_link, decrypt_tut_data
from .common.hashing import hash_bytes
from .opaque_bundle import OpaqueBundleHandler

logger = logging.getLogger(__name__)

_HAPP_LINK_RE = re.compile(r"happ://(?:crypt3|crypt2|crypt)/[^\s<>\"']+", re.IGNORECASE)


class HatHandler(OpaqueBundleHandler):
    """HA Tunnel Plus blobs with optional non-destructive decryption metadata.

    The encrypted/raw source file is always the canonical record because the
    inherited builder republishes source blobs. Deep inspection enriches that
    record; it never replaces the blob identity with an unbuildable logical
    link record.
    """

    def __init__(self, raw_store: RawStore):
        super().__init__(raw_store, "hat")

    def detect(self, filename: str, data: bytes) -> bool:
        if filename.lower().endswith((".hat", ".happ")):
            return True
        return b"happ://" in data.lower()

    def parse(
        self,
        raw_data: bytes,
        source_info: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        source_info = source_info or {}
        raw_hash = hash_bytes(raw_data)
        data: Dict[str, Any] = {
            "filename": source_info.get("filename", f"{raw_hash}.hat"),
            "blob_hash": raw_hash,
            "size": len(raw_data),
        }
        text = raw_data.decode("utf-8", "ignore")

        decrypted_links: list[dict[str, str]] = []
        for link in dict.fromkeys(_HAPP_LINK_RE.findall(text)):
            try:
                decrypted = decrypt_happ_link(link)
            except Exception as exc:
                logger.debug("HAPP link decryption failed: %s", exc)
                continue
            if decrypted:
                decrypted_links.append({"line": link, "decrypted": decrypted})
        if decrypted_links:
            data["happ_links"] = decrypted_links

        # Some .hat files use the same three-part PBKDF2/AES-GCM envelope as
        # TMT. Treat this as metadata only so missing credentials cannot make
        # the original file disappear from the build.
        if "." in text and len(text) > 50:
            try:
                decrypted = decrypt_tut_data(text, extension=".tmt")
            except MissingSecretError:
                logger.debug(
                    "HAT/TMT decryption credential is not configured; preserving opaque blob"
                )
            except Exception as exc:
                logger.debug("HAT/TMT deep parsing failed: %s", exc)
            else:
                if decrypted:
                    data["content"] = text
                    data["decrypted"] = decrypted

        return [
            {
                "type": self.format_id,
                "unique_hash": raw_hash,
                "data": data,
            }
        ]
