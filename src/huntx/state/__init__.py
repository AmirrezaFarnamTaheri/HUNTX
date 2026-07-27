"""Durable state package.

The compatibility installer keeps the public ``StateRepo`` import stable while
activating hardened operations for every import path, including direct imports
from ``huntx.state.repo``.
"""

from .repo import StateRepo
from .repo_hardening import install_state_repo_hardening

install_state_repo_hardening(StateRepo)

__all__ = ["StateRepo"]
