import logging
from typing import List, Dict, Any, Optional
from .opaque_bundle import OpaqueBundleHandler
from ..store.raw_store import RawStore
from .common.crypto import decrypt_tut_data
from .common.hashing import hash_string

logger = logging.getLogger(__name__)


class TmtHandler(OpaqueBundleHandler):
    """
    Handler for .tmt files.
    """

    def __init__(self, raw_store: RawStore):
        super().__init__(raw_store, "tmt")

    def parse(self, raw_data: bytes, source_info: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if source_info is None:
            source_info = {}
        try:
            text = raw_data.decode("utf-8", "ignore")
            if "." in text and len(text) > 50:
                decrypted = decrypt_tut_data(text, extension=".tmt")
                if decrypted:
                    return [
                        {
                            "type": self.format_id,
                            "unique_hash": hash_string(text),
                            "data": {"content": text, "decrypted": decrypted},
                        }
                    ]
        except Exception as e:
            logger.debug(f"TMT deep parsing failed: {e}")

        return super().parse(raw_data, source_info)
