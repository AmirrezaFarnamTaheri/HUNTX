from .opaque_bundle import OpaqueBundleHandler
from ..store.raw_store import RawStore

class Npv4Handler(OpaqueBundleHandler):
    def __init__(self, raw_store: RawStore):
        super().__init__(raw_store, "npv4")
