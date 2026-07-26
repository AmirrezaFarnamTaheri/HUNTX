"""Hardening tests for ``TelegramPublisher``.

Covers three defects found in the audit:

1. ``filename`` was interpolated raw into a ``Content-Disposition``
   quoted-string, so a name containing ``"`` or CR/LF could escape the
   parameter or terminate the header and smuggle extra multipart parts.
2. An API-supplied ``retry_after`` was passed straight to ``time.sleep`` with
   no ceiling and no type check — a hostile/buggy value could park a bounded
   publish worker indefinitely, and a JSON string raised ``TypeError``.
3. The malformed-token warning echoed a prefix of the bot token into logs.
"""

import os
import unittest
from unittest.mock import patch

from huntx.publishers.telegram.publisher import (
    TelegramPublisher,
    _coerce_retry_after,
    _safe_multipart_filename,
)


class TestMultipartFilenameSanitization(unittest.TestCase):
    def test_plain_generated_name_is_preserved(self):
        # The names this pipeline actually generates must survive unchanged.
        name = "route1_npvt_abc12345.zip"
        self.assertEqual(_safe_multipart_filename(name), name)

    def test_quote_is_removed(self):
        out = _safe_multipart_filename('evil".txt')
        self.assertNotIn('"', out)

    def test_crlf_is_removed(self):
        out = _safe_multipart_filename("a\r\nContent-Type: text/html\r\n\r\nb.txt")
        self.assertNotIn("\r", out)
        self.assertNotIn("\n", out)

    def test_backslash_and_path_separators_removed(self):
        out = _safe_multipart_filename("..\\..\\etc/passwd")
        self.assertNotIn("\\", out)
        self.assertNotIn("/", out)

    def test_empty_name_falls_back(self):
        self.assertTrue(_safe_multipart_filename(""))

    def test_output_never_contains_header_breaking_chars(self):
        hostile = 'x";\r\n--boundary\r\nContent-Disposition: form-data; name="y"\r\n\r\nz'
        out = _safe_multipart_filename(hostile)
        for bad in ('"', "\r", "\n", ";", "\\"):
            self.assertNotIn(bad, out, f"{bad!r} survived sanitization")


class TestRetryAfterCoercion(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("HUNTX_PUBLISH_MAX_RETRY_AFTER_SECONDS")
        os.environ.pop("HUNTX_PUBLISH_MAX_RETRY_AFTER_SECONDS", None)

    def tearDown(self):
        os.environ.pop("HUNTX_PUBLISH_MAX_RETRY_AFTER_SECONDS", None)
        if self._saved is not None:
            os.environ["HUNTX_PUBLISH_MAX_RETRY_AFTER_SECONDS"] = self._saved

    def test_reasonable_value_accepted(self):
        self.assertEqual(_coerce_retry_after(5), 5)

    def test_numeric_string_accepted(self):
        # Telegram may serialize it as a string; it must not reach time.sleep raw.
        self.assertEqual(_coerce_retry_after("5"), 5)

    def test_non_numeric_rejected(self):
        self.assertIsNone(_coerce_retry_after("soon"))

    def test_none_and_zero_and_negative_rejected(self):
        for value in (None, 0, -1):
            self.assertIsNone(_coerce_retry_after(value), f"accepted {value!r}")

    def test_bool_rejected(self):
        # bool is an int subclass; True must not become a 1-second sleep.
        self.assertIsNone(_coerce_retry_after(True))

    def test_value_over_ceiling_rejected(self):
        # The whole point: a 24h request must not park a publish worker.
        self.assertIsNone(_coerce_retry_after(86400))

    def test_ceiling_is_configurable(self):
        os.environ["HUNTX_PUBLISH_MAX_RETRY_AFTER_SECONDS"] = "120"
        self.assertEqual(_coerce_retry_after(90), 90)

    def test_invalid_ceiling_falls_back_to_default(self):
        os.environ["HUNTX_PUBLISH_MAX_RETRY_AFTER_SECONDS"] = "not-a-number"
        self.assertEqual(_coerce_retry_after(5), 5)
        self.assertIsNone(_coerce_retry_after(86400))


class TestTokenNotLogged(unittest.TestCase):
    def test_malformed_token_warning_omits_token_material(self):
        token = "ABCDEFGHIJ_supersecret"  # no colon -> triggers the warning
        with patch("huntx.publishers.telegram.publisher.logger") as mock_logger:
            TelegramPublisher(token)
            self.assertTrue(mock_logger.warning.called)
            logged = " ".join(str(a) for a in mock_logger.warning.call_args[0])
        self.assertNotIn("ABCDE", logged)
        self.assertNotIn(token, logged)


if __name__ == "__main__":
    unittest.main()
