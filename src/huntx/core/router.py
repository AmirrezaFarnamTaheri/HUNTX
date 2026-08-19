import base64
import binascii
import re
from functools import lru_cache

_PROXY_SCHEMES = ('vmess://', 'vless://', 'trojan://', 'ss://', 'ssr://', 'hysteria2://', 'hy2://', 'hysteria2+realm://', 'hysteria2+realm+http://', 'hysteria://', 'tuic://', 'wireguard://', 'wg://', 'socks://', 'socks5://', 'socks4://', 'socks4a://', 'anytls://', 'juicity://', 'warp://', 'dns://', 'dnstt://', 'ssh://', 'shadowtls://', 'naive://', 'naive+https://')
_PROXY_URI_PREFIXES = _PROXY_SCHEMES
_AUTH_HTTP_PROXY_RE = re.compile('https?://[^@\\s/:]+(?::[^@\\s]*)?@(?:\\[[^\\]]+\\]|[^/\\s:]+):\\d{1,5}(?:#[^\\s<>\\"\']*)?', re.IGNORECASE)


@lru_cache(maxsize=4096)
def _format_by_extension(filename_lower: str) -> str | None:
    """Cache extension-based format lookups — filenames repeat heavily across runs."""
    if filename_lower.endswith('.ovpn'):
        return 'ovpn'
    if filename_lower.endswith('.npv4'):
        return 'npv4'
    if filename_lower.endswith('.conf'):
        return 'conf_lines'
    if filename_lower.endswith('.ehi'):
        return 'ehi'
    if filename_lower.endswith('.hc'):
        return 'hc'
    if filename_lower.endswith('.hat'):
        return 'hat'
    if filename_lower.endswith('.sip'):
        return 'sip'
    if filename_lower.endswith('.nm'):
        return 'nm'
    if filename_lower.endswith('.dark'):
        return 'dark'
    if filename_lower.endswith('.tut'):
        return 'tut'
    if filename_lower.endswith('.sks'):
        return 'sks'
    if filename_lower.endswith('.tmt'):
        return 'tmt'
    if filename_lower.endswith('.npvtsub'):
        return 'npvtsub'
    return None


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
