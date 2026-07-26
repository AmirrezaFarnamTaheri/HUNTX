import logging
import re
from typing import List, Dict, Any, Optional
from .opaque_bundle import OpaqueBundleHandler
from ..store.raw_store import RawStore
from .common.crypto import decrypt_happ_link, decrypt_tut_data
from .common.hashing import hash_string

logger = logging.getLogger(__name__)


class HatHandler(OpaqueBundleHandler):
    """
    Handler for HA Tunnel Plus (.hat) and HA Tunnel (.happ) links.
    Moves beyond opaque bundling by decrypting happ:// links found in text.
    """
    def __init__(self, raw_store: RawStore):
        super().__init__(raw_store, "hat")

    def detect(self, filename: str, data: bytes) -> bool:
        if filename.endswith(".hat") or filename.endswith(".happ"):
            return True
        # Also detect if it's a text file containing happ:// links
        try:
            text = data.decode("utf-8", "ignore")
            if "happ://" in text:
                return True
        except Exception:
            pass
        return False

    def parse(self, raw_data: bytes, source_info: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if source_info is None:
            source_info = {}
        # First, try as a text file with links
        try:
            text = raw_data.decode("utf-8", "ignore")
            links = re.findall(r"happ://[a-zA-Z0-9/._-]+", text)
            if links:
                records = []
                for link in links:
                    decrypted = decrypt_happ_link(link)
                    if decrypted:
                        # Decrypted HAT links often contain JSON or structured text
                        records.append({
                            "type": self.format_id,
                            "unique_hash": hash_string(link),
                            "data": {
                                "line": link,
                                "decrypted": decrypted
                            }
                        })
                if records:
                    return records
        except Exception:
            pass

        # Try decrypting as a .tut/.tmt format (some .hat are actually these)
        try:
            # "strip" is not a registered codec error handler; because handlers
            # are resolved lazily, any .hat containing a single invalid UTF-8
            # byte raised LookupError here, which the broad `except Exception`
            # below swallowed — silently disabling this entire .tut/.tmt
            # fallback branch for exactly the binary-ish files it exists to
            # handle. "ignore" is the intended behavior.
            text = raw_data.decode("utf-8", "ignore")
            if "." in text and len(text) > 50:
                decrypted = decrypt_tut_data(text, extension=".tmt")
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
