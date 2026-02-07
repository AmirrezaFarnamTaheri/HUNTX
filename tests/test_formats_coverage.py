import unittest
from unittest.mock import MagicMock
from mergebot.formats.npvt import NpvtHandler
from mergebot.formats.conf_lines import ConfLinesHandler
from mergebot.formats.opaque_bundle import OpaqueBundleHandler

class TestFormatsCoverage(unittest.TestCase):
    def test_npvt_format(self):
        fmt = NpvtHandler()

        # Test parse normal
        content = b"vless://uuid@host:443?key=val#remark\nvmess://base64"
        lines = fmt.parse(content, {})
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["data"]["line"], "vless://uuid@host:443?key=val#remark")

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
