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

    # Content based heuristics
    try:
        text_preview = content[:1024].decode("utf-8", errors="ignore")
        if "vless://" in text_preview or "vmess://" in text_preview or "trojan://" in text_preview:
            return "npvt"
    except:
        pass

    # Default fallback
    return "opaque_bundle"
