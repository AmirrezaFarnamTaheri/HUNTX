from .opaque_bundle import OpaqueBundleHandler
from ..store.raw_store import RawStore


class EhiHandler(OpaqueBundleHandler):
    def __init__(self, raw_store: RawStore):
        super().__init__(raw_store, "ehi")
