import base64
import binascii
import re
from functools import lru_cache

_PROXY_SCHEMES = ('vmess://', 'vless://', 'trojan://', 'ss://', 'ssr://', 'hysteria2://', 'hy2://', 'hysteria2+realm://', 'hysteria2+realm+http://', 'hysteria://', 'tuic://', 'wireguard://', 'wg://', 'socks://', 'socks5://', 'socks4://', 'socks4a://', 'anytls://', 'juicity://', 'mieru://', 'mierus://', 'warp://', 'dns://', 'dnstt://', 'ssh://', 'shadowtls://', 'naive+https://', 'naive+quic://')
_PROXY_URI_PREFIXES = _PROXY_SCHEMES
_AUTH_HTTP_PROXY_RE = re.compile('https?://[^@\\s/:]+(?::[^@\\s]*)?@(?:\\[[^\\]]+\\]|[^/\\s:]+):\\d{1,5}(?:#[^\\s<>\\"\']*)?', re.IGNORECASE)


_EXTENSION_FORMAT_MAP = {
    ".ovpn": "ovpn",
    ".npv4": "npv4",
    ".conf": "conf_lines",
    ".ehi": "ehi",
    ".hc": "hc",
    ".hat": "hat",
    ".sip": "sip",
    ".nm": "nm",
    ".dark": "dark",
    ".tut": "tut",
    ".sks": "sks",
    ".tmt": "tmt",
    ".npvtsub": "npvtsub",
}


@lru_cache(maxsize=4096)
def _format_by_extension(filename_lower: str) -> str | None:
    """Cache extension-based format lookups — filenames repeat heavily across runs."""
    _, dot, ext = filename_lower.rpartition(".")
    return _EXTENSION_FORMAT_MAP.get(f".{ext}") if dot else None


def _contains_proxy_uri(text: str) -> bool:
    """Return whether text contains a safe proxy endpoint URI."""
    return any((scheme in text for scheme in _PROXY_URI_PREFIXES)) or bool(_AUTH_HTTP_PROXY_RE.search(text))


def decide_format(filename: str, content: bytes) -> str:
    """
    Decide the format ID based on filename extension and content.

    Ordinary HTTP(S) links are deliberately not enough to classify content as
    ``npvt``; only authenticated endpoint-shaped HTTP proxy URLs are used by
    the content heuristic.
    """
    ext_fmt = _format_by_extension(filename.lower())
    if ext_fmt is not None:
        return ext_fmt
    text_preview = content[:2048].decode('utf-8', errors='ignore')
    if _contains_proxy_uri(text_preview):
        return 'npvt'
    clean = text_preview.strip()
    if clean and '://' not in clean and (' ' not in clean) and (len(clean) > 20):
        try:
            decoded = base64.b64decode(clean[:512] + '==').decode('utf-8', errors='ignore')
            if _contains_proxy_uri(decoded):
                return 'npvt'
        except (binascii.Error, ValueError):
            pass
    return 'opaque_bundle'
