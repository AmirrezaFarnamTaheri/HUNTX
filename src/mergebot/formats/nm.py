from .opaque_bundle import OpaqueBundleHandler


class NmHandler(OpaqueBundleHandler):
    """NetMod VPN Client encrypted config files (.nm).
    Supports SSH, V2Ray/Xray, SSL/TLS, OpenVPN, DNSTT tunneling.
    Files may be locked/private — treated as opaque binary bundles."""

    @property
    def format_id(self) -> str:
        return "nm"
