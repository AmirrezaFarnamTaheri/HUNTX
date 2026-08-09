"""Tests for the serialized stale-lease reclamation (TOCTOU fix).

The reclamation path must (a) reclaim a genuinely stale lease, (b) never touch
a fresh/live lease, and (c) refuse to reclaim while another reaper holds the
``.reap`` marker — which is what prevents a late ``os.replace`` from one waiter
clobbering a live lease created by another.
"""

import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from huntx.core.session_lease import (
    _acquire_reap_lock,
    _is_stale,
    _remove_if_stale,
    session_lease_path,
)


class TestReapLogic(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.path = session_lease_path(self.root, "identity")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_lease(self, age_seconds: float):
        self.path.write_text("owner", encoding="utf-8")
        mtime = time.time() - age_seconds
        os.utime(self.path, (mtime, mtime))

    def test_fresh_lease_is_not_reclaimed(self):
        self._write_lease(age_seconds=0)
        self.assertFalse(_remove_if_stale(self.path, stale_after_seconds=3600, now=time.time()))
        self.assertTrue(self.path.exists())

    def test_stale_lease_is_reclaimed(self):
        self._write_lease(age_seconds=10_000)
        self.assertTrue(_remove_if_stale(self.path, stale_after_seconds=3600, now=time.time()))
        self.assertFalse(self.path.exists())

    def test_missing_lease_is_noop(self):
        self.assertFalse(_remove_if_stale(self.path, stale_after_seconds=1, now=time.time()))

    def test_active_reap_marker_blocks_reclamation(self):
        # Simulate a concurrent reaper holding a fresh .reap marker: our
        # reclamation must decline rather than clobber, leaving the lease intact.
        self._write_lease(age_seconds=10_000)
        reap_marker = self.path.with_name(f"{self.path.name}.reap")
        reap_marker.write_text("busy", encoding="utf-8")
        try:
            self.assertFalse(_remove_if_stale(self.path, stale_after_seconds=3600, now=time.time()))
            self.assertTrue(self.path.exists())
        finally:
            reap_marker.unlink(missing_ok=True)

    def test_expired_reap_marker_is_force_reclaimed(self):
        # A .reap marker older than the TTL means the reaper died; it must be
        # reclaimable so reaping cannot wedge permanently.
        reap_marker = self.path.with_name(f"{self.path.name}.reap")
        reap_marker.write_text("dead", encoding="utf-8")
        old = time.time() - 10_000
        os.utime(reap_marker, (old, old))
        self.assertTrue(_acquire_reap_lock(reap_marker))
        # We now own it; clean up.
        reap_marker.unlink(missing_ok=True)

    def test_is_stale_boundary(self):
        # Deterministic now + mtime set to exactly `now - stale_after_seconds`
        # so this actually exercises the equality boundary of `_is_stale`'s
        # strict `>` comparison — a fuzzier now/mtime pairing (e.g. writing at
        # one time.time() call and reading at another) can't catch a `>` to
        # `>=` regression, since a small elapsed gap masks the true boundary.
        now = 10_000.0
        self.path.write_text("owner", encoding="utf-8")
        os.utime(self.path, (now - 100, now - 100))
        self.assertFalse(_is_stale(self.path, stale_after_seconds=100, now=now))
        self.assertTrue(_is_stale(self.path, stale_after_seconds=10, now=now))


if __name__ == "__main__":
    unittest.main()
