"""Durable state package.

The compatibility installers keep the public ``StateRepo`` import stable while
activating hardened operations for every import path.
"""

from .repo import StateRepo
from .repo_hardening import install_state_repo_hardening
from .consumer_reconciliation import install_consumer_reconciliation

install_state_repo_hardening(StateRepo)
install_consumer_reconciliation(StateRepo)

__all__ = ["StateRepo"]
