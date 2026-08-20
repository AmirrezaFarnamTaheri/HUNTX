"""Durable state package.

The compatibility installers keep the public ``StateRepo`` import stable while
activating hardened operations and migration safety for every import path.
"""

from .repo import StateRepo
from .repo_hardening import install_state_repo_hardening
from .consumer_reconciliation import install_consumer_reconciliation
from .migration_safety import install_migration_safety

# These handlers inherit OpaqueBundleHandler and therefore require their raw
# source blobs at build time just like the original opaque/archive formats.
# Keep this compatibility extension local until the hardening layer is folded
# into StateRepo proper. ``setattr`` avoids narrowing the original tuple's
# literal arity in static analysis while preserving the runtime class contract.
setattr(
    StateRepo,
    "_BLOB_DEPENDENT_FORMATS",
    tuple(dict.fromkeys((*StateRepo._BLOB_DEPENDENT_FORMATS, "tut", "sks", "tmt"))),
)

install_migration_safety(__import__("huntx.state.db", fromlist=["DBConnection"]).DBConnection)
install_state_repo_hardening(StateRepo)
install_consumer_reconciliation(StateRepo)

__all__ = ["StateRepo"]
