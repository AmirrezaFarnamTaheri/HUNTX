from .opaque_bundle import OpaqueBundleHandler
from ..store.raw_store import RawStore


class DarkHandler(OpaqueBundleHandler):
    """Dark Tunnel VPN encrypted config files (.dark).
    Proprietary binary format — treated as opaque binary bundles."""

    def __init__(self, raw_store: RawStore):
        super().__init__(raw_store, "dark")
