"""TLS JA4/JA4S Fingerprinting & Active DPI-Resilience Classifier.

Authority:
    FoxIO JA4+ Network Fingerprinting Specification: https://github.com/FoxIO-LLC/ja4
    RFC 8446 (TLS 1.3): https://datatracker.ietf.org/doc/html/rfc8446
    RFC 7301 (ALPN): https://datatracker.ietf.org/doc/html/rfc7301
"""
import hashlib
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass
class TLSProfileScore:
    """Statistical DPI-resilience and stealth classification of a node."""
    dpi_resilience: int
    is_stealth: bool
    ja4s_fingerprint: Optional[str]
    has_sni: bool
    has_alpn: bool
    security_layer: str


class TLSClassifier:
    """Analyzes TLS parameters and evaluates active firewall detection risk."""

    def compute_ja4s(
        self,
        tls_version: str,
        alpn: str,
        num_extensions: int,
        ciphers: List[int],
        extensions: List[int]
    ) -> str:
        """Compute standard FoxIO JA4S server fingerprint."""
        # Section A: Protocol (t) + Version (13/12) + ALPN (2 chars) + Ext Count (2 hex digits)
        alpn_clean = alpn.strip().lower()
        alpn_tag = (alpn_clean[:1] + alpn_clean[-1:]
                    ) if len(alpn_clean) >= 2 else (alpn_clean.ljust(2, "0") if alpn_clean else "00")
        sec_a = f"t{tls_version}{alpn_tag}{num_extensions:02d}"

        # Section B: Cipher Hash (first 12 chars of SHA-256 over comma-separated hex ciphers)
        ciphers_str = ",".join(f"{c:04x}" for c in ciphers)
        sec_b = hashlib.sha256(ciphers_str.encode("utf-8")).hexdigest()[:12]

        # Section C: Extension Hash (first 12 chars of SHA-256 over comma-separated hex extensions)
        ext_str = ",".join(f"{e:04x}" for e in extensions)
        sec_c = hashlib.sha256(ext_str.encode("utf-8")).hexdigest()[:12]

        return f"{sec_a}_{sec_b}_{sec_c}"

    def score_node_resilience(self, node: Dict[str, Any]) -> TLSProfileScore:
        """Evaluate deep-packet inspection (DPI) resilience for proxy nodes."""
        security = str(node.get("security", "")).lower()
        has_tls = bool(node.get("tls", False)) or security in ("tls", "reality")
        sni = str(node.get("sni", "")).strip()
        alpn = str(node.get("alpn", "")).strip()
        proto = str(node.get("protocol", "")).lower()

        score = 0
        is_stealth = False

        if security == "reality" or node.get("pbk"):
            score = 95
            is_stealth = True
        elif proto == "hysteria2":
            score = 90
            is_stealth = True
        elif has_tls:
            score = 65
            if sni:
                score += 10
            if alpn and ("h2" in alpn or "h3" in alpn):
                score += 10
            if score >= 80:
                is_stealth = True
        else:
            # Plain Shadowsocks / VMess TCP without TLS
            score = 25
            is_stealth = False

        return TLSProfileScore(
            dpi_resilience=min(100, score),
            is_stealth=is_stealth,
            ja4s_fingerprint=None,
            has_sni=bool(sni),
            has_alpn=bool(alpn),
            security_layer=security or ("tls" if has_tls else "none")
        )
