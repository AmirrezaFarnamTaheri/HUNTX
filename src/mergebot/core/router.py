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

    # .npvtsub is a subscription text (VLESS/VMESS/Trojan URIs)
    if fn.endswith(".npvtsub"):
        return "npvtsub"

    # Content based heuristics
    try:
        text_preview = content[:1024].decode("utf-8", errors="ignore")
        if "vless://" in text_preview or "vmess://" in text_preview or "trojan://" in text_preview:
            return "npvt"
    except Exception:
        pass

    # Default fallback
    return "opaque_bundle"
