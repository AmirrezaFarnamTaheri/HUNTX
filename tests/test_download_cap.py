"""Regression tests for the hard download byte cap in the Bot API connector.

The pre-download size check trusts API-reported ``file_size`` metadata; these
tests prove the cap is also enforced on the bytes actually received, so a
document that under-reports its size cannot force an unbounded in-memory read.
"""

import unittest
from unittest.mock import MagicMock, patch

from huntx.connectors.telegram.connector import (
    MAX_DOWNLOAD_BYTES,
    TelegramConnector,
)


def _response_with(payload: bytes) -> MagicMock:
    """Build a context-manager mock mimicking urlopen's bounded read(amt)."""
    resp = MagicMock()
    resp.read.side_effect = lambda amt=None: payload if amt is None else payload[:amt]
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestDownloadCap(unittest.TestCase):
    def setUp(self):
        self.conn = TelegramConnector("123:abc", "-1001")

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_normal_download_within_cap(self, mock_urlopen, _sleep):
        mock_urlopen.return_value = _response_with(b"payload-bytes")
        self.assertEqual(self.conn._download_file("path/x"), b"payload-bytes")

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_oversized_body_is_rejected(self, mock_urlopen, _sleep):
        # One byte over the cap: the read is bounded to MAX+1, and the result
        # must be discarded rather than buffered/propagated.
        oversized = b"x" * (MAX_DOWNLOAD_BYTES + 1)
        mock_urlopen.return_value = _response_with(oversized)
        self.assertIsNone(self.conn._download_file("path/x"))

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_exact_cap_size_is_accepted(self, mock_urlopen, _sleep):
        exact = b"y" * MAX_DOWNLOAD_BYTES
        mock_urlopen.return_value = _response_with(exact)
        self.assertEqual(self.conn._download_file("path/x"), exact)

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_read_is_called_with_bounded_amount(self, mock_urlopen, _sleep):
        resp = _response_with(b"data")
        mock_urlopen.return_value = resp
        self.conn._download_file("path/x")
        (amt,) = resp.read.call_args.args
        self.assertEqual(amt, MAX_DOWNLOAD_BYTES + 1)


if __name__ == "__main__":
    unittest.main()
