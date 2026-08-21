"""Real-Time Dynamic AI Proxy Router (Multi-Armed Bandit / UCB1).

Authority:
    Auer, Cesa-Bianchi, Fischer (2002): Finite-time Analysis of the Multiarmed Bandit Problem.
    Machine Learning, 47, 235–256.
"""
import math
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class RouterArmStats:
    """Statistical tracker for an individual proxy node arm."""
    pull_count: int = 0
    total_reward: float = 0.0
    average_reward: float = 0.0
    last_latency_ms: float = 0.0

    def update(self, reward: float, latency_ms: float) -> None:
        """Update arm statistics with observed reward and latency."""
        self.pull_count += 1
        self.total_reward += reward
        self.average_reward = self.total_reward / self.pull_count
        self.last_latency_ms = latency_ms

class UCB1ProxyRouter:
    """Multi-Armed Bandit router balancing latency exploitation and exploration."""

    def __init__(self, exploration_constant: float = 1.414):
        self.exploration_constant = exploration_constant
        self.arms: Dict[str, RouterArmStats] = {}
        self.total_pulls: int = 0

    def select_node(self, candidates: List[str]) -> Optional[str]:
        """Select optimal proxy node candidate using UCB1 policy."""
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        # 1. Cold start: test any candidate that hasn't been pulled yet
        for node in candidates:
            stats = self.arms.get(node)
            if not stats or stats.pull_count == 0:
                return node

        # 2. Compute UCB1 score for all evaluated candidates
        best_node = candidates[0]
        best_score = -float("inf")
        ln_total = math.log(max(1, self.total_pulls))

        for node in candidates:
            stats = self.arms[node]
            exploration_bonus = self.exploration_constant * math.sqrt(ln_total / stats.pull_count)
            ucb_score = stats.average_reward + exploration_bonus

            if ucb_score > best_score:
                best_score = ucb_score
                best_node = node

        return best_node

    def record_reward(self, node_id: str, latency_ms: float, is_success: bool = True) -> None:
        """Record outcome and calculate normalized non-linear reward."""
        if node_id not in self.arms:
            self.arms[node_id] = RouterArmStats()

        # Non-linear latency reward bounded in [0.0, 1.0]
        # Low latency (<50ms) -> ~0.95; High latency (>500ms) -> <0.66
        if not is_success:
            reward = 0.0
        else:
            reward = 1000.0 / (1000.0 + max(0.0, latency_ms))

        self.arms[node_id].update(reward, latency_ms)
        self.total_pulls += 1
