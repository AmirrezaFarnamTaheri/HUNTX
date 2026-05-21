import logging
from typing import List, Dict, Any, Optional
from .base import FormatHandler
from .common.crypto import decrypt_netmod_data
from .common.hashing import hash_bytes
from ..store.raw_store import RawStore


logger = logging.getLogger(__name__)


class NmHandler(FormatHandler):
    """
    NetMod VPN Client encrypted config files (.nm).
    Supports SSH, V2Ray/Xray, SSL/TLS, OpenVPN, DNSTT tunneling.
    Decrypted using AES-ECB with key from Pantegnos.
    """

    def __init__(self, raw_store: RawStore, format_id: str = "nm"):
        self.raw_store = raw_store
        self._format_id = format_id

    @property
    def format_id(self) -> str:
        return self._format_id

    def parse(self, raw_data: bytes, source_info: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if source_info is None:
            source_info = {}
        try:
            decrypted = decrypt_netmod_data(raw_data)
            if decrypted:
                return [{
                    "type": self.format_id,
                    "unique_hash": hash_bytes(raw_data),
                    "data": {
                        "content": raw_data.hex(),
                        "decrypted": decrypted
                    }
                }]
        except Exception as e:
            logger.debug(f"NetMod parsing failed: {e}")
            
        return []

    def build(self, records: List[Dict[str, Any]]) -> bytes:
        raise NotImplementedError("Building .nm files is not supported.")

