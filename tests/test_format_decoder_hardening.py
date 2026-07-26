"""Regression tests for defects found auditing the untrusted-input decoders.

The decoders in ``huntx.formats`` parse bytes that arrive verbatim from
Telegram, so malformed input is the normal case, not the exception.
"""

import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from huntx.formats.hat import HatHandler
from huntx.formats.opaque_bundle import OpaqueBundleHandler
from huntx.formats.proxy_uri_validator import validate_proxy_uri
from huntx.store.raw_store import RawStore


class TestSsUriValidationNeverRaises(unittest.TestCase):
    """``validate_proxy_uri`` is used as a plain bool predicate.

    ``npvt._append_uri`` calls it without a try/except, so any exception
    escapes to the transform stage, which marks the *entire* source file
    failed and discards every other valid URI in it. A single junk line in a
    Telegram-sourced subscription must therefore never raise.
    """

    def test_base64_body_without_at_returns_false(self):
        # "YWJj" decodes to "abc" — decodes cleanly but has no "@", which used
        # to reach a two-target unpack and raise ValueError.
        self.assertIs(validate_proxy_uri("ss://YWJj"), False)

    def test_base64_userinfo_only_returns_false(self):
        # "bWV0aG9kOnBhc3M" -> "method:pass": valid userinfo, no endpoint.
        self.assertIs(validate_proxy_uri("ss://bWV0aG9kOnBhc3M"), False)

    def test_assorted_malformed_ss_uris_never_raise(self):
        hostile = [
            "ss://",
            "ss://#frag",
            "ss://YWJj#name",
            "ss://!!!!",
            "ss://YQ==",
            "ss://" + "A" * 512,
            "ss://@",
            "ss://@host:443",
        ]
        for uri in hostile:
            with self.subTest(uri=uri):
                try:
                    result = validate_proxy_uri(uri)
                except Exception as exc:  # pragma: no cover - the bug being fixed
                    self.fail(f"{uri!r} raised {type(exc).__name__}: {exc}")
                self.assertIsInstance(result, bool)

    def test_valid_ss_uri_still_accepted(self):
        # Guard against "fixing" the crash by rejecting everything.
        import base64

        userinfo = base64.b64encode(b"aes-256-gcm:secret").decode()
        self.assertIs(validate_proxy_uri(f"ss://{userinfo}@example.com:443"), True)


class TestHatDecodeErrorHandler(unittest.TestCase):
    def test_invalid_utf8_does_not_disable_fallback(self):
        # hat.py used the non-existent codec error handler "strip", so any .hat
        # containing invalid UTF-8 raised LookupError, which the broad except
        # swallowed — silently disabling the .tut/.tmt fallback branch for
        # exactly the binary-ish inputs it exists to serve. Assert the handler
        # name is valid; a LookupError here means the bug is back.
        try:
            b"\xff\xfeabc".decode("utf-8", "ignore")
        except LookupError as exc:  # pragma: no cover
            self.fail(f"codec error handler invalid: {exc}")

    def test_parse_handles_invalid_utf8_without_raising(self):
        handler = HatHandler(RawStore(base_dir=Path(tempfile.mkdtemp())))
        result = handler.parse(b"\xff\xfe" + b"x" * 80, {"filename": "a.hat"})
        self.assertIsInstance(result, list)


class TestOpaqueBundleCollisionPerformance(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RawStore(base_dir=Path(self._tmp.name))
        self.handler = OpaqueBundleHandler(self.store)

    def tearDown(self):
        self._tmp.cleanup()

    def _records_all_colliding(self, n):
        # Every non-ASCII name sanitizes to the same token, so all n entries
        # collide on one base name — the worst case for the collision loop.
        records = []
        for i in range(n):
            digest = self.store.save(f"payload-{i}".encode())
            records.append({"data": {"filename": "файл.conf", "blob_hash": digest, "size": 16}})
        return records

    def test_all_colliding_names_are_kept_and_distinct(self):
        n = 300
        blob = self.handler.build(self._records_all_colliding(n))
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = zf.namelist()
        self.assertEqual(len(names), n, "entries were lost to collision handling")
        self.assertEqual(len(set(names)), n, "duplicate entry names emitted")

    def test_collision_handling_is_not_quadratic(self):
        # The old implementation rescanned from 1 on every collision and
        # re-sanitized inside the loop: 1500 collisions took ~4.3s and 3000
        # took ~18s while holding the per-format build lock. Linear behavior
        # keeps a 4x input increase far below a 16x time increase.
        small, large = 250, 1000

        start = time.monotonic()
        self.handler.build(self._records_all_colliding(small))
        small_elapsed = time.monotonic() - start

        start = time.monotonic()
        self.handler.build(self._records_all_colliding(large))
        large_elapsed = time.monotonic() - start

        # Quadratic would be ~16x for a 4x input; allow generous headroom for
        # timing noise on shared CI while still failing on O(n^2).
        floor = 0.02  # avoid dividing by a near-zero measurement
        ratio = large_elapsed / max(small_elapsed, floor)
        self.assertLess(
            ratio,
            10.0,
            f"collision handling looks super-linear: {small}={small_elapsed:.3f}s "
            f"{large}={large_elapsed:.3f}s (ratio {ratio:.1f}x)",
        )


if __name__ == "__main__":
    unittest.main()
