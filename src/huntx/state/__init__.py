"""Durable state package.

The compatibility installers keep the public ``StateRepo`` import stable while
activating hardened operations and migration safety for every import path.
"""

from .repo import StateRepo
from .repo_hardening import install_state_repo_hardening
from .consumer_reconciliation import install_consumer_reconciliation
from .migration_safety import install_migration_safety

install_migration_safety(__import__("huntx.state.db", fromlist=["DBConnection"]).DBConnection)
install_state_repo_hardening(StateRepo)
install_consumer_reconciliation(StateRepo)

__all__ = ["StateRepo"]
