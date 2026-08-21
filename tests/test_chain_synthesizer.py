# Tests for Multi-Hop Dynamic Chain Synthesizer (Python Plane)
from huntx.pipeline.chain import DynamicChainSynthesizer, ChainStrategy, SynthesizedProxyChain

def test_chain_strategy_enum():
    assert ChainStrategy.LOWEST_LATENCY.value == "lowest_latency"
    assert ChainStrategy.DOMESTIC_RELAY_INTERNATIONAL_EXIT.value == "domestic_relay_international_exit"
    assert ChainStrategy.MULTI_REGION_MESH.value == "multi_region_mesh"

def test_chain_synthesizer_rejects_empty_or_single_node():
    synth = DynamicChainSynthesizer()
    assert synth.synthesize([]) == []
    assert synth.synthesize([{"server": "1.1.1.1", "port": 443, "protocol": "vless"}]) == []

def test_chain_synthesizer_domestic_relay_international_exit():
    synth = DynamicChainSynthesizer(strategy=ChainStrategy.DOMESTIC_RELAY_INTERNATIONAL_EXIT, domestic_country="IR")
    nodes = [
        {"id": "n1", "server": "185.1.1.1", "port": 443, "protocol": "vless", "country": "IR", "ping": 15, "alive": True},
        {"id": "n2", "server": "104.16.1.1", "port": 443, "protocol": "vless", "country": "DE", "ping": 45, "alive": True},
        {"id": "n3", "server": "8.8.8.8", "port": 8443, "protocol": "hysteria2", "country": "US", "ping": 110, "alive": True},
        {"id": "n4", "server": "185.2.2.2", "port": 443, "protocol": "trojan", "country": "IR", "ping": 20, "alive": False}, # Dead
    ]
    chains = synth.synthesize(nodes)
    assert len(chains) > 0
    first_chain = chains[0]
    assert isinstance(first_chain, SynthesizedProxyChain)
    assert first_chain.relay_node["country"] == "IR"
    assert first_chain.exit_node["country"] != "IR"
    assert first_chain.composite_latency_ms == first_chain.relay_node["ping"] + first_chain.exit_node["ping"]

def test_chain_synthesizer_loop_prevention():
    synth = DynamicChainSynthesizer(strategy=ChainStrategy.LOWEST_LATENCY)
    nodes = [
        {"id": "n1", "server": "1.1.1.1", "port": 443, "protocol": "vless", "country": "DE", "ping": 30, "alive": True},
        {"id": "n2", "server": "1.1.1.1", "port": 443, "protocol": "vless", "country": "DE", "ping": 30, "alive": True}, # Same address
    ]
    chains = synth.synthesize(nodes)
    # Should not pair identical servers together
    for c in chains:
        assert c.relay_node["server"] != c.exit_node["server"]
