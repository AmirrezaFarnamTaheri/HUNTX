from .opaque_bundle import OpaqueBundleHandler


class DarkHandler(OpaqueBundleHandler):
    """Dark Tunnel VPN encrypted config files (.dark).
    Proprietary binary format — treated as opaque binary bundles."""

    @property
    def format_id(self) -> str:
        return "dark"
