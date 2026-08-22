"""Real-Time BGP Peering & ASN Latency Map Integrator.

Authority:
    RFC 4271 (A Border Gateway Protocol 4): https://datatracker.ietf.org/doc/html/rfc4271
    PeeringDB API Specification: https://peeringdb.com/apidocs/
"""
from dataclasses import dataclass
from enum import Enum
from typing import Set


class ASNTier(str, Enum):
    """Hierarchical classification of Autonomous Systems."""
    TIER_1 = "tier_1"        # Settlement-free global backbone (Lumen, Telia, Cogent, NTT, HE)
    TIER_2 = "tier_2"        # Regional Transit / Content Providers (Cloudflare, Fastly, Akamai)
    EYEBALL = "eyeball"      # Last-mile retail / Consumer ISPs
    UNKNOWN = "unknown"


# Canonical Tier 1 Global Transit Backbones
TIER_1_ASNS: Set[int] = {
    174,   # Cogent Communications
    701,   # Verizon / UUNET
    1239,  # Sprint / T-Mobile
    1299,  # Arelion (Telia Carrier)
    2914,  # NTT America
    3257,  # GTT Communications
    3320,  # Deutsche Telekom
    3356,  # Lumen / Level 3
    3491,  # PCCW Global
    5511,  # Orange
    6453,  # Tata Communications
    6461,  # Zayo
    6762,  # Telecom Italia Sparkle
    6939,  # Hurricane Electric
    7018,  # AT&T
}

# Major Content Delivery Networks & Hyperscalers
TIER_2_ASNS: Set[int] = {
    13335,  # Cloudflare
    15169,  # Google
    16509,  # Amazon AWS
    8075,  # Microsoft Azure
    20940,  # Akamai
    54113,  # Fastly
    24940,  # Hetzner
    16276,  # OVH
    31898,  # Oracle Cloud
}


@dataclass
class CarrierQualityScore:
    """Evaluated upstream transit capability and congestion profile."""
    asn: int
    as_org: str
    tier: ASNTier
    quality_index: int
    congestion_risk: str
    is_tier1_transit: bool


class BGPPeeringIntegrator:
    """Maps BGP topology and ranks proxy routes based on autonomous system connectivity."""

    def classify_asn_tier(self, asn: int) -> ASNTier:
        """Classify ASN into Tier 1, Tier 2, or Eyeball."""
        if not asn or asn <= 0:
            return ASNTier.UNKNOWN
        if asn in TIER_1_ASNS:
            return ASNTier.TIER_1
        if asn in TIER_2_ASNS:
            return ASNTier.TIER_2
        return ASNTier.EYEBALL

    def score_carrier_quality(self, asn: int, as_org: str = "", base_rtt: float = 50.0) -> CarrierQualityScore:
        """Compute composite carrier quality index for an endpoint."""
        tier = self.classify_asn_tier(asn)
        quality = 50

        if tier == ASNTier.TIER_1:
            quality = 95
            congestion_risk = "low"
        elif tier == ASNTier.TIER_2:
            quality = 85
            congestion_risk = "low"
        else:  # Eyeball
            quality = 55
            congestion_risk = "medium" if base_rtt < 80 else "high"

        # Apply latency penalty if base RTT exceeds acceptable SLA
        if base_rtt > 150:
            quality = max(20, quality - 25)
        elif base_rtt < 40:
            quality = min(100, quality + 5)

        return CarrierQualityScore(
            asn=asn,
            as_org=as_org or f"AS{asn}",
            tier=tier,
            quality_index=quality,
            congestion_risk=congestion_risk,
            is_tier1_transit=(tier == ASNTier.TIER_1)
        )
