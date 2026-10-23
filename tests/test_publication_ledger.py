import hashlib
import tempfile
import unittest
from pathlib import Path

from huntx.state.db import open_db
from huntx.state.repo import StateRepo


class TestPublicationLedger(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = StateRepo(open_db(Path(self._tmp.name) / "state.db"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_destination_confirmations_are_independent_and_idempotent(self):
        artifact = hashlib.sha256(b"payload").hexdigest()
        intent = self.repo.ensure_publication_intent(
            "route:fmt",
            artifact,
            generation="gen-1",
        )
        self.assertFalse(self.repo.is_delivery_confirmed(intent, "primary"))
        self.assertFalse(self.repo.is_delivery_confirmed(intent, "backup"))

        self.repo.mark_delivery_confirmed(intent, "primary", remote_receipt="42")
        self.repo.mark_delivery_confirmed(intent, "primary", remote_receipt="42")

        self.assertTrue(self.repo.is_delivery_confirmed(intent, "primary"))
        self.assertFalse(self.repo.is_delivery_confirmed(intent, "backup"))
        with self.repo.db.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM publication_deliveries " "WHERE intent_id = ? AND destination_id = 'primary'",
                (intent,),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_changed_generation_creates_new_delivery_intent(self):
        artifact = hashlib.sha256(b"payload").hexdigest()
        first = self.repo.ensure_publication_intent("route:fmt", artifact, generation="gen-1")
        second = self.repo.ensure_publication_intent("route:fmt", artifact, generation="gen-2")
        self.assertNotEqual(first, second)

    def test_crashed_send_remains_unconfirmed_in_durable_ledger(self):
        artifact = hashlib.sha256(b"payload").hexdigest()
        intent = self.repo.ensure_publication_intent(
            "route:fmt", artifact, generation="crash-generation",
        )
        self.repo.mark_delivery_sending(intent, "primary")
        # A fresh connection represents a production worker restarting.
        self.assertEqual(self.repo.get_delivery_state(intent, "primary"), "sending")
        self.assertFalse(self.repo.is_delivery_confirmed(intent, "primary"))

    def test_unknown_delivery_outcome_is_persisted(self):
        artifact = hashlib.sha256(b"payload").hexdigest()
        intent = self.repo.ensure_publication_intent(
            "route:fmt",
            artifact,
            generation="gen-1",
        )
        self.repo.mark_delivery_failed(
            intent,
            "primary",
            error_class="UnknownPublicationOutcome",
            unknown_outcome=True,
        )

        self.assertEqual(
            self.repo.get_delivery_state(intent, "primary"),
            "unknown_outcome",
        )

    def test_claim_is_atomic_across_independent_connections(self):
        """Only one worker can own a remote side effect for one destination."""
        from concurrent.futures import ThreadPoolExecutor
        import threading

        digest = hashlib.sha256(b"parallel").hexdigest()
        intent = self.repo.ensure_publication_intent("route:fmt", digest, generation="parallel")
        barrier = threading.Barrier(8)

        def attempt(number):
            repo = StateRepo(self.repo.db)
            barrier.wait(timeout=5)
            return repo.mark_delivery_sending(intent, "primary", attempt_token=f"worker-{number}")

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(self.repo.get_delivery_state(intent, "primary"), "sending")

    def test_attempt_fencing_and_audited_reconciliation(self):
        digest = hashlib.sha256(b"ambiguous").hexdigest()
        intent = self.repo.ensure_publication_intent("route:fmt", digest, generation="reconcile")
        self.assertTrue(self.repo.mark_delivery_sending(intent, "primary", attempt_token="first"))
        self.assertFalse(self.repo.mark_delivery_sending(intent, "primary", attempt_token="second"))
        self.repo.mark_delivery_failed(
            intent, "primary", attempt_token="first",
            error_class="UnknownPublicationOutcome", unknown_outcome=True,
        )
        self.assertFalse(self.repo.mark_delivery_sending(intent, "primary", attempt_token="second"))
        with self.assertRaises(ValueError):
            self.repo.reconcile_delivery(
                intent, "primary", outcome="confirmed", operator="oncall", reason="no receipt",
            )
        self.repo.reconcile_delivery(
            intent, "primary", outcome="not_delivered", operator="oncall",
            reason="confirmed no matching message in destination history",
        )
        self.assertTrue(self.repo.mark_delivery_sending(intent, "primary", attempt_token="second"))
        with self.assertRaises(RuntimeError):
            self.repo.mark_delivery_confirmed(intent, "primary", attempt_token="first", remote_receipt="1")
        self.repo.mark_delivery_confirmed(intent, "primary", attempt_token="second", remote_receipt="2")
        with self.repo.db.connect() as conn:
            rows = conn.execute(
                "SELECT operator, resulting_state FROM publication_delivery_reconciliations "
                "WHERE intent_id=?", (intent,),
            ).fetchall()
        self.assertEqual([(row["operator"], row["resulting_state"]) for row in rows],
                         [("oncall", "failed")])
