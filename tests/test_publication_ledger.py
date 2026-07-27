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
