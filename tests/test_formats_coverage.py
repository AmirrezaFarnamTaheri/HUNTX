import unittest
from unittest.mock import MagicMock
from huntx.formats.npvt import NpvtHandler
from huntx.formats.npvtsub import NpvtSubHandler
from huntx.formats.conf_lines import ConfLinesHandler
from huntx.formats.opaque_bundle import OpaqueBundleHandler
from huntx.formats.ehi import EhiHandler
from huntx.formats.hc import HcHandler
from huntx.formats.hat import HatHandler
from huntx.formats.sip import SipHandler


class TestFormatsCoverage(unittest.TestCase):
    def test_npvt_format(self):
        fmt = NpvtHandler()

        # Test parse normal
        content = b"vless://uuid@host:443?key=val#remark\nvmess://base64"
        lines = fmt.parse(content, {})
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["data"]["line"], "vless://uuid@host:443?key=val")

        # Test parse base64
        import base64

        b64_content = base64.b64encode(content).decode("utf-8")
        lines_b64 = fmt.parse(b64_content.encode("utf-8"), {})
        self.assertEqual(len(lines_b64), 2)

        # Test build
        built = fmt.build(lines)
        self.assertIn(b"vless://", built)
        self.assertIn(b"vmess://", built)

    def test_conf_lines_format(self):
        fmt = ConfLinesHandler()

        content = b"line1\n#comment\nline2"
        lines = fmt.parse(content, {})
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["data"]["line"], "line1")
        self.assertEqual(lines[1]["data"]["line"], "line2")

        built = fmt.build(lines)
        self.assertEqual(built, b"line1\nline2")

    def test_opaque_bundle_format(self):
        mock_store = MagicMock()
        fmt = OpaqueBundleHandler(mock_store)

        data = b"binarydata"
        mock_store.get.return_value = data

        parsed = fmt.parse(data, {"filename": "file.bin"})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["data"]["filename"], "file.bin")
        self.assertEqual(parsed[0]["data"]["size"], len(data))

        # Build
        mock_store.get.return_value = data
        built = fmt.build(parsed)
        self.assertTrue(built.startswith(b"PK"))

        # Verify zip content roughly (could import zipfile to verify really)
        import zipfile
        import io

        with zipfile.ZipFile(io.BytesIO(built)) as zf:
            self.assertIn("file.bin", zf.namelist())
            self.assertEqual(zf.read("file.bin"), data)

    def test_npvtsub_format(self):
        fmt = NpvtSubHandler()
        self.assertEqual(fmt.format_id, "npvtsub")

        content = b"vless://uuid@host:443#tag\nvmess://base64\ngarbage"
        records = fmt.parse(content, {})
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["data"]["line"], "vless://uuid@host:443")

        # Test base64 decode path
        import base64

        plain = b"vless://a@b:1\ntrojan://c@d:2"
        b64 = base64.b64encode(plain)
        records_b64 = fmt.parse(b64, {})
        self.assertEqual(len(records_b64), 2)

        # Test build deduplicates
        built = fmt.build(records)
        self.assertIn(b"vless://", built)
        self.assertIn(b"vmess://", built)
        self.assertNotIn(b"garbage", built)

    def test_ehi_handler(self):
        mock_store = MagicMock()
        fmt = EhiHandler(mock_store)
        self.assertEqual(fmt.format_id, "ehi")

        data = b"ehi_binary_data"
        mock_store.get.return_value = data
        parsed = fmt.parse(data, {"filename": "tunnel.ehi"})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["data"]["filename"], "tunnel.ehi")

        built = fmt.build(parsed)
        self.assertTrue(built.startswith(b"PK"))

    def test_hc_handler(self):
        mock_store = MagicMock()
        fmt = HcHandler(mock_store)
        self.assertEqual(fmt.format_id, "hc")

        data = b"hc_binary_data"
        mock_store.get.return_value = data
        parsed = fmt.parse(data, {"filename": "config.hc"})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["data"]["filename"], "config.hc")

    def test_hat_handler(self):
        mock_store = MagicMock()
        fmt = HatHandler(mock_store)
        self.assertEqual(fmt.format_id, "hat")

        data = b"hat_binary_data"
        mock_store.get.return_value = data
        parsed = fmt.parse(data, {"filename": "proxy.hat"})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["data"]["filename"], "proxy.hat")

    def test_sip_handler(self):
        mock_store = MagicMock()
        fmt = SipHandler(mock_store)
        self.assertEqual(fmt.format_id, "sip")

        data = b"sip_binary_data"
        mock_store.get.return_value = data
        parsed = fmt.parse(data, {"filename": "account.sip"})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["data"]["filename"], "account.sip")
