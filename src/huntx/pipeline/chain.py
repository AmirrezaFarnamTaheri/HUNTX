"""Multi-Hop Dynamic Proxy Chain Synthesizer.

Authority:
    RFC 1928 (SOCKS Protocol Version 5): https://datatracker.ietf.org/doc/html/rfc1928
    Sing-box Dial Fields Specification: https://sing-box.sagernet.org/configuration/shared/dial/
"""
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any

class ChainStrategy(str, Enum):
    """Synthesis strategy heuristics for multi-hop mesh generation."""
    LOWEST_LATENCY = "lowest_latency"
    DOMESTIC_RELAY_INTERNATIONAL_EXIT = "domestic_relay_international_exit"
    MULTI_REGION_MESH = "multi_region_mesh"

@dataclass
class SynthesizedProxyChain:
    """Represents a composite multi-hop proxy forwarding chain."""
    chain_id: str
    relay_node: Dict[str, Any]
    exit_node: Dict[str, Any]
    composite_latency_ms: float
    strategy: ChainStrategy

    def to_dict(self) -> Dict[str, Any]:
        """Convert synthesized chain to JSON serializable representation."""
        return {
            "chain_id": self.chain_id,
            "relay": self.relay_node,
            "exit": self.exit_node,
            "composite_latency_ms": self.composite_latency_ms,
            "strategy": self.strategy.value
        }

class DynamicChainSynthesizer:
    """Evaluates node pools and pairs relays with egress nodes."""

    def __init__(
        self,
        strategy: ChainStrategy = ChainStrategy.LOWEST_LATENCY,
        domestic_country: str = "IR",
        max_composite_latency_ms: float = 1200.0,
        max_chains: int = 20
    ):
        self.strategy = strategy
        self.domestic_country = domestic_country.upper()
        self.max_composite_latency_ms = max_composite_latency_ms
        self.max_chains = max_chains

    def synthesize(self, nodes: List[Dict[str, Any]]) -> List[SynthesizedProxyChain]:
        """Synthesize valid multi-hop proxy chains from a candidate pool."""
        alive_nodes = [
            n for n in nodes
            if n.get("alive", True) and n.get("server") and n.get("port")
        ]

        if len(alive_nodes) < 2:
            return []

        candidates: List[SynthesizedProxyChain] = []

        if self.strategy == ChainStrategy.DOMESTIC_RELAY_INTERNATIONAL_EXIT:
            relays = [n for n in alive_nodes if str(n.get("country", "")).upper() == self.domestic_country]
            exits = [n for n in alive_nodes if str(n.get("country", "")).upper() != self.domestic_country]

            for r in relays:
                for x in exits:
                    if r.get("server") == x.get("server"):
                        continue
                    latency = float(r.get("ping", 50)) + float(x.get("ping", 100))
                    if latency <= self.max_composite_latency_ms:
                        candidates.append(SynthesizedProxyChain(
                            chain_id=f"chain-{r.get('id', 'r')}-{x.get('id', 'x')}",
                            relay_node=r,
                            exit_node=x,
                            composite_latency_ms=latency,
                            strategy=self.strategy
                        ))
        elif self.strategy == ChainStrategy.MULTI_REGION_MESH:
            for i, r in enumerate(alive_nodes):
                for x in alive_nodes[i + 1:]:
                    r_ctry = str(r.get("country", "")).upper()
                    x_ctry = str(x.get("country", "")).upper()
                    if r_ctry and x_ctry and r_ctry == x_ctry:
                        continue # Require diverse regions
                    if r.get("server") == x.get("server"):
                        continue
                    latency = float(r.get("ping", 50)) + float(x.get("ping", 50))
                    if latency <= self.max_composite_latency_ms:
                        candidates.append(SynthesizedProxyChain(
                            chain_id=f"chain-{r.get('id', 'r')}-{x.get('id', 'x')}",
                            relay_node=r,
                            exit_node=x,
                            composite_latency_ms=latency,
                            strategy=self.strategy
                        ))
        else: # LOWEST_LATENCY
            for i, r in enumerate(alive_nodes):
                for x in alive_nodes[i + 1:]:
                    if r.get("server") == x.get("server"):
                        continue
                    latency = float(r.get("ping", 50)) + float(x.get("ping", 50))
                    if latency <= self.max_composite_latency_ms:
                        candidates.append(SynthesizedProxyChain(
                            chain_id=f"chain-{r.get('id', 'r')}-{x.get('id', 'x')}",
                            relay_node=r,
                            exit_node=x,
                            composite_latency_ms=latency,
                            strategy=self.strategy
                        ))

        # Sort by lowest composite latency
        candidates.sort(key=lambda c: c.composite_latency_ms)
        return candidates[:self.max_chains]
