"""Reconcile a manually verified Telegram delivery outcome in the publication ledger.

Do not infer non-delivery from elapsed time. Inspect the remote destination
and supply independent evidence before making an uncertain attempt retryable.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from huntx.state.db import open_db
from huntx.state.repo import StateRepo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="Production state database path")
    parser.add_argument("--intent-id", type=int, required=True)
    parser.add_argument("--destination-id", required=True, help="Full stable@config-hash ID")
    parser.add_argument("--outcome", choices=("confirmed", "not_delivered"), required=True)
    parser.add_argument("--receipt", help="Verified Telegram message receipt when confirmed")
    parser.add_argument("--operator", required=True)
    parser.add_argument("--reason", required=True, help="Evidence reference; never guess")
    args = parser.parse_args()
    StateRepo(open_db(args.db)).reconcile_delivery(
        args.intent_id, args.destination_id,
        outcome=args.outcome, operator=args.operator,
        reason=args.reason, remote_receipt=args.receipt,
    )
    print("Publication outcome reconciled and audited.")


if __name__ == "__main__":
    main()
