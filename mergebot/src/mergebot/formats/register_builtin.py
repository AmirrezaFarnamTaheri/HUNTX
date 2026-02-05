from .registry import FormatRegistry
from ..store.raw_store import RawStore
from .conf_lines import ConfLinesHandler
from .npvt import NpvtHandler
from .ovpn import OvpnHandler
from .npv4 import Npv4Handler
from .opaque_bundle import OpaqueBundleHandler

def register_all_formats(registry: FormatRegistry, raw_store: RawStore):
    registry.register(ConfLinesHandler())
    registry.register(NpvtHandler())
    registry.register(OvpnHandler(raw_store))
    registry.register(Npv4Handler(raw_store))
    # Register generic opaque bundle for unknowns if needed
    registry.register(OpaqueBundleHandler(raw_store, "opaque_bundle"))
