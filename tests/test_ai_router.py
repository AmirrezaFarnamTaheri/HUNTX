# Tests for Real-Time Dynamic AI Proxy Router (MAB / UCB1)
# Authority: Lai & Robbins (1985), Auer et al. (2002) Finite-time Analysis of Multiarmed Bandit
from huntx.pipeline.ai_router import UCB1ProxyRouter

def test_router_initialization_and_cold_start():
    router = UCB1ProxyRouter(exploration_constant=1.414)
    nodes = ["node-1", "node-2", "node-3"]
    
    # Cold start: should pick all nodes sequentially to explore initial baseline
    selected = set()
    for _ in range(3):
        arm = router.select_node(nodes)
        selected.add(arm)
        router.record_reward(arm, latency_ms=100.0)
    
    assert selected == {"node-1", "node-2", "node-3"}

def test_router_converges_to_lowest_latency_node():
    router = UCB1ProxyRouter(exploration_constant=0.5)
    nodes = ["fast-node", "slow-node"]

    # Initial explore
    for n in nodes:
        router.select_node(nodes)
        router.record_reward(n, latency_ms=30.0 if n == "fast-node" else 300.0)

    # Subsequent 50 selections: fast-node should dominate selections
    fast_count = 0
    for _ in range(50):
        chosen = router.select_node(nodes)
        if chosen == "fast-node":
            fast_count += 1
            router.record_reward(chosen, latency_ms=30.0)
        else:
            router.record_reward(chosen, latency_ms=300.0)

    assert fast_count > 40

def test_router_handles_empty_or_single_node():
    router = UCB1ProxyRouter()
    assert router.select_node([]) is None
    assert router.select_node(["single-node"]) == "single-node"
