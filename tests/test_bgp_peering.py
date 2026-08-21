# Tests for BGP Peering & ASN Carrier Quality Integrator
# Authority: PeeringDB API & RFC 4271 (A Border Gateway Protocol 4)
from huntx.pipeline.bgp import BGPPeeringIntegrator, ASNTier, CarrierQualityScore

def test_asn_tier_classification():
    integrator = BGPPeeringIntegrator()
    # Tier 1 ASNs (Level3/Lumen, Telia/Arelion, Cogent, NTT, HE)
    assert integrator.classify_asn_tier(3356) == ASNTier.TIER_1 # Lumen / Level 3
    assert integrator.classify_asn_tier(1299) == ASNTier.TIER_1 # Arelion / Telia
    assert integrator.classify_asn_tier(174) == ASNTier.TIER_1  # Cogent
    assert integrator.classify_asn_tier(2914) == ASNTier.TIER_1 # NTT
    assert integrator.classify_asn_tier(13335) == ASNTier.TIER_2 # Cloudflare CDN
    assert integrator.classify_asn_tier(58224) == ASNTier.EYEBALL # Iran Telecommunication Company

def test_carrier_quality_evaluation():
    integrator = BGPPeeringIntegrator()
    # High-tier cloud node
    score_tier1 = integrator.score_carrier_quality(asn=3356, as_org="LUMEN-LEGACY", base_rtt=35.0)
    assert isinstance(score_tier1, CarrierQualityScore)
    assert score_tier1.tier == ASNTier.TIER_1
    assert score_tier1.quality_index >= 90
    assert score_tier1.congestion_risk == "low"

    # Eyeball ISP with high hop transit
    score_eyeball = integrator.score_carrier_quality(asn=58224, as_org="TCI", base_rtt=120.0)
    assert score_eyeball.tier == ASNTier.EYEBALL
    assert score_eyeball.quality_index <= 60
