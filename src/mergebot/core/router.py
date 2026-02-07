import logging

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

    # New formats
    # .ehi, .hc, .hat, .sip are typically binary or app-specific configs -> opaque_bundle
    if fn.endswith(".ehi") or fn.endswith(".hc") or fn.endswith(".hat") or fn.endswith(".sip"):
        return "opaque_bundle"

    # .npvtsub is likely a subscription text (VLESS/VMESS)
    if fn.endswith(".npvtsub"):
        try:
            text_preview = content[:1024].decode("utf-8", errors="ignore")
            if "vless://" in text_preview or "vmess://" in text_preview or "trojan://" in text_preview:
                return "npvt"
        except:
            pass
        return "opaque_bundle"

    # Content based heuristics
    try:
        text_preview = content[:1024].decode("utf-8", errors="ignore")
        if "vless://" in text_preview or "vmess://" in text_preview or "trojan://" in text_preview:
            return "npvt"
    except:
        pass

    # Default fallback
    return "opaque_bundle"
