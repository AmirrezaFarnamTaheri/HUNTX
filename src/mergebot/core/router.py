# All known proxy URI schemes for content-based detection
_PROXY_URI_PREFIXES = (
    "vmess://", "vless://", "trojan://",
    "ss://", "ssr://",
    "hysteria2://", "hy2://", "hysteria://",
    "tuic://",
    "wireguard://", "wg://",
    "socks://", "socks5://", "socks4://",
    "anytls://",
    "juicity://",
    "warp://",
    "dns://", "dnstt://",
)


def decide_format(filename: str, content: bytes) -> str:
    """
    Decides the format ID based on filename extension and content.
    """
    fn = filename.lower()

    # Extension based
    if fn.endswith(".ovpn"):
        return "ovpn"
    if fn.endswith(".npv4"):
        return "npv4"
    if fn.endswith(".conf"):
        return "conf_lines"

    # Dedicated opaque/binary formats
    if fn.endswith(".ehi"):
        return "ehi"
    if fn.endswith(".hc"):
        return "hc"
    if fn.endswith(".hat"):
        return "hat"
    if fn.endswith(".sip"):
        return "sip"
    if fn.endswith(".nm"):
        return "nm"
    if fn.endswith(".dark"):
        return "dark"

    # .npvtsub is a subscription text (VLESS/VMESS/Trojan URIs)
    if fn.endswith(".npvtsub"):
        return "npvtsub"

    # Content based heuristics — detect proxy URI lines
    try:
        text_preview = content[:2048].decode("utf-8", errors="ignore")
        if any(scheme in text_preview for scheme in _PROXY_URI_PREFIXES):
            return "npvt"
        # Also detect base64-encoded subscription content
        clean = text_preview.strip()
        if clean and "://" not in clean and " " not in clean and len(clean) > 20:
            import base64
            try:
                decoded = base64.b64decode(clean[:512] + "==").decode("utf-8", errors="ignore")
                if any(scheme in decoded for scheme in _PROXY_URI_PREFIXES):
                    return "npvt"
            except Exception:
                pass
    except Exception:
        pass

    # Default fallback
    return "opaque_bundle"
