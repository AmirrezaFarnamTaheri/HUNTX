import logging
from typing import List, Dict, Any, Optional
from .opaque_bundle import OpaqueBundleHandler
from ..store.raw_store import RawStore
from .common.crypto import decrypt_tut_data
from .common.hashing import hash_string

logger = logging.getLogger(__name__)


class Npv4Handler(OpaqueBundleHandler):
    """
    Handler for NapsternetV v4 (.npv4).
    Moves beyond opaque bundling by attempting deep inspection via decryption.
    """
    def __init__(self, raw_store: RawStore):
        super().__init__(raw_store, "npv4")

    def parse(self, raw_data: bytes, source_info: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if source_info is None:
            source_info = {}
        # Try as a .tut/.sks/.tmt compatible format
        try:
            text = raw_data.decode("utf-8", "ignore")
            if "." in text and len(text) > 50:
                decrypted = decrypt_tut_data(text, extension=".sks") # sks often shares logic with npv4
                if decrypted:
                    return [{
                        "type": self.format_id,
                        "unique_hash": hash_string(text),
                        "data": {
                            "content": text,
                            "decrypted": decrypted
                        }
                    }]
        except Exception:
            pass

        # Fallback to opaque bundle (ZIP)
        return super().parse(raw_data, source_info)
