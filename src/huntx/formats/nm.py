from .opaque_bundle import OpaqueBundleHandler
from ..store.raw_store import RawStore


class NmHandler(OpaqueBundleHandler):
    """NetMod VPN Client encrypted config files (.nm).
    Supports SSH, V2Ray/Xray, SSL/TLS, OpenVPN, DNSTT tunneling.
    Files may be locked/private — treated as opaque binary bundles."""

    def __init__(self, raw_store: RawStore):
        super().__init__(raw_store, "nm")
