from .registry import FormatRegistry
from ..store.raw_store import RawStore
from .conf_lines import ConfLinesHandler
from .npvt import NpvtHandler
from .npvtsub import NpvtSubHandler
from .ovpn import OvpnHandler
from .npv4 import Npv4Handler
from .ehi import EhiHandler
from .hc import HcHandler
from .hat import HatHandler
from .sip import SipHandler
from .nm import NmHandler
from .dark import DarkHandler
from .opaque_bundle import OpaqueBundleHandler


def register_all_formats(registry: FormatRegistry, raw_store: RawStore):
    registry.register(ConfLinesHandler())
    registry.register(NpvtHandler())
    registry.register(NpvtSubHandler())
    registry.register(OvpnHandler(raw_store))
    registry.register(Npv4Handler(raw_store))
    registry.register(EhiHandler(raw_store))
    registry.register(HcHandler(raw_store))
    registry.register(HatHandler(raw_store))
    registry.register(SipHandler(raw_store))
    registry.register(NmHandler(raw_store))
    registry.register(DarkHandler(raw_store))
    registry.register(OpaqueBundleHandler(raw_store, "opaque_bundle"))
