import logging
import re
from typing import Any, Dict, List, Optional

from .common.crypto import MissingSecretError, decrypt_slipnet_link
from .common.hashing import hash_string

logger = logging.getLogger(__name__)

V1 = [
    "Version",
    "Tunnel Type/Mode",
    "Name",
    "Domain",
    "Resolvers",
    "AuthMode",
    "KeepAlive",
    "CC",
    "Port",
    "Host",
    "GSO",
]
V20 = V1 + [
    "DNSTT Public Key",
    "SOCKS Username",
    "SOCKS Password",
    "SSH Enabled",
    "SSH Username",
    "SSH Password",
    "SSH Port",
    "Forward DNS thru SSH",
    "SSH Host",
    "Use Server DNS",
    "DoH URL",
    "DNS Transport",
    "SSH Auth Type",
    "SSH Private Key (B64)",
    "SSH Key Passphrase (B64)",
    "Tor Bridge Lines (B64)",
    "DNSTT Authoritative",
    "Naive Port",
    "Naive Username",
    "Naive Password (B64)",
    "Is Locked",
    "Lock Password Hash",
    "Expiration Date",
    "Allow Sharing",
    "Bound Device ID",
    "Resolvers Hidden",
    "Hidden Resolvers",
    "NoizDNS Stealth",
    "DNS Payload Size",
    "SOCKS5 Server Port",
    "VayDNS DNSTT Compat",
    "VayDNS Record Type",
    "VayDNS Max Qname Len",
    "VayDNS RPS",
    "VayDNS Idle Timeout",
    "VayDNS Keepalive",
    "VayDNS UDP Timeout",
    "VayDNS Max Num Labels",
    "VayDNS Client Id Size",
]
V21 = V20 + [
    "SSH TLS Enabled",
    "SSH TLS SNI",
    "SSH HTTP Proxy Host",
    "SSH HTTP Proxy Port",
    "SSH HTTP Proxy Custom Host",
    "SSH WS Enabled",
    "SSH WS Path",
    "SSH WS Use TLS",
    "SSH WS Custom Host",
]
V22 = V21 + ["SSH Payload (B64)"]
V24 = V22 + ["Resolver Mode", "RR Spread Count"]
V25 = V24 + [
    "VLESS UUID",
    "VLESS Security",
    "VLESS Transport",
    "VLESS WS Path",
    "CDN IP",
    "CDN Port",
    "SNI Fragment Enabled",
    "SNI Fragment Strategy",
    "SNI Fragment Delay MS",
    "Legacy SNI (Empty)",
]
V27 = V25 + [
    "CH Padding Enabled",
    "WS Header Obfuscation",
    "WS Padding Enabled",
    "SNI Spoof TTL",
    "Fake Decoy Host",
    "TCP Max Seg",
]
V28 = V27 + ["VLESS SNI"]

SCHEMAS = {
    "1": V1,
    "20": V20,
    "21": V21,
    "22": V22,
    "23": V24,
    "24": V24,
    "25": V25,
    "26": V27,
    "27": V27,
    "28": V28,
}

BOOLEAN_FIELDS = {
    "Is Locked",
    "SSH TLS Enabled",
    "SSH WS Enabled",
    "SSH WS Use TLS",
    "SNI Fragment Enabled",
    "CH Padding Enabled",
    "WS Header Obfuscation",
    "WS Padding Enabled",
    "VayDNS DNSTT Compat",
    "Resolvers Hidden",
    "GSO",
    "DNSTT Authoritative",
    "SSH Enabled",
    "Forward DNS thru SSH",
    "Use Server DNS",
    "Allow Sharing",
    "NoizDNS Stealth",
}


class SlipNetHandler:
    """SlipNet encrypted links with optional versioned profile enrichment."""

    def __init__(self, format_id: str = "slipnet"):
        self._format_id = format_id

    @property
    def format_id(self) -> str:
        return self._format_id

    def detect(self, filename: str, data: bytes) -> bool:
        try:
            return "slipnet-enc://" in data.decode("utf-8", "ignore")
        except Exception:
            return False

    def parse(
        self,
        raw_data: bytes,
        source_info: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        del source_info
        text = raw_data.decode("utf-8", "ignore")
        links = re.findall(r"slipnet-enc://[a-zA-Z0-9+/=_\-]+", text)

        records: List[Dict[str, Any]] = []
        for link in links:
            data: Dict[str, Any] = {"line": link}
            try:
                decrypted = decrypt_slipnet_link(link)
            except MissingSecretError:
                logger.debug(
                    "SlipNet decryption credential is not configured; preserving encrypted link"
                )
                decrypted = None
            except Exception as exc:
                logger.debug("SlipNet deep parsing failed: %s", exc)
                decrypted = None

            if decrypted:
                data["decrypted"] = decrypted
                data["profile"] = self._parse_profile(decrypted)

            records.append(
                {
                    "type": self.format_id,
                    "unique_hash": hash_string(link),
                    "data": data,
                }
            )
        return records

    def build(self, records: List[Dict[str, Any]]) -> bytes:
        """Rebuild a deterministic newline-delimited set of encrypted links."""
        lines: List[str] = []
        seen: set[str] = set()
        for record in records:
            line = record.get("data", {}).get("line")
            if not isinstance(line, str) or not line.startswith("slipnet-enc://"):
                continue
            if line in seen:
                continue
            seen.add(line)
            lines.append(line)
        if not lines:
            return b""
        return ("\n".join(lines) + "\n").encode("utf-8")

    def _parse_profile(self, decrypted_text: str) -> Dict[str, Any]:
        """Parse a decrypted pipe-separated profile into a structured mapping."""
        decrypted_text = decrypted_text.rstrip("|")
        parts = decrypted_text.split("|")
        if not parts:
            return {}

        version_str = parts[0]
        schema = SCHEMAS.get(version_str)
        profile: Dict[str, Any] = {"Version": version_str}

        for index, value in enumerate(parts):
            if index == 0:
                continue
            label = schema[index] if schema and index < len(schema) else f"Field_{index}"
            profile[label] = value == "1" if label in BOOLEAN_FIELDS else value

        return profile
