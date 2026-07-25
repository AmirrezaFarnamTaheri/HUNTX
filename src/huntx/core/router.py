import base64
import binascii
from functools import lru_cache

# All known proxy URI schemes for content-based detection
_PROXY_SCHEMES = (
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
_PROXY_URI_PREFIXES = _PROXY_SCHEMES


@lru_cache(maxsize=4096)
def _format_by_extension(filename_lower: str) -> str | None:
    """Cache extension-based format lookups — filenames repeat heavily across runs."""
    if filename_lower.endswith(".ovpn"):
        return "ovpn"
    if filename_lower.endswith(".npv4"):
        return "npv4"
    if filename_lower.endswith(".conf"):
        return "conf_lines"
    if filename_lower.endswith(".ehi"):
        return "ehi"
    if filename_lower.endswith(".hc"):
        return "hc"
    if filename_lower.endswith(".hat"):
        return "hat"
    if filename_lower.endswith(".sip"):
        return "sip"
    if filename_lower.endswith(".nm"):
        return "nm"
    if filename_lower.endswith(".dark"):
        return "dark"
    if filename_lower.endswith(".tut"):
        return "tut"
    if filename_lower.endswith(".sks"):
        return "sks"
    if filename_lower.endswith(".tmt"):
        return "tmt"
    if filename_lower.endswith(".npvtsub"):
        return "npvtsub"
    return None


def decide_format(filename: str, content: bytes) -> str:
    """
    Decides the format ID based on filename extension and content.
    Extension checks are LRU-cached; content heuristics run only for unknowns.
    """
    ext_fmt = _format_by_extension(filename.lower())
    if ext_fmt is not None:
        return ext_fmt

    # Content based heuristics — detect proxy URI lines
    text_preview = content[:2048].decode("utf-8", errors="ignore")
    if any(scheme in text_preview for scheme in _PROXY_URI_PREFIXES):
        return "npvt"
    # Also detect base64-encoded subscription content
    clean = text_preview.strip()
    if clean and "://" not in clean and " " not in clean and len(clean) > 20:
        try:
            decoded = base64.b64decode(clean[:512] + "==").decode("utf-8", errors="ignore")
            if any(scheme in decoded for scheme in _PROXY_URI_PREFIXES):
                return "npvt"
        except (binascii.Error, ValueError):
            pass

    # Default fallback
    return "opaque_bundle"
