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
from huntx.formats.ovpn import OvpnHandler
from huntx.formats.dark import DarkHandler
from huntx.formats.nm import NmHandler
from huntx.formats.npv4 import Npv4Handler
from huntx.formats.tut import TutHandler
from huntx.formats.sks import SksHandler
from huntx.formats.tmt import TmtHandler
from huntx.formats.slipnet import SlipNetHandler


class TestFormatsCoverage(unittest.TestCase):
    def test_b64_decode_shared_helper(self):
        import base64
        import binascii
        from huntx.formats.common.b64 import b64_decode

        payload = "hello:world"
        enc_padded = base64.b64encode(payload.encode()).decode()
        self.assertEqual(b64_decode(enc_padded), payload)

        enc_stripped = enc_padded.rstrip("=")
        self.assertEqual(b64_decode(enc_stripped), payload)

        enc_urlsafe = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
        self.assertEqual(b64_decode(enc_urlsafe), payload)

        with self.assertRaises((binascii.Error, ValueError)):
            b64_decode("!@#$%^&*()")

    def test_npvt_format(self):
        import base64
        import json

        fmt = NpvtHandler()
        user_id = "11111111-1111-4111-8111-111111111111"
        vmess_payload = {
            "v": "2",
            "add": "vmess.example.com",
            "port": "443",
            "id": "22222222-2222-4222-8222-222222222222",
            "aid": "0",
            "net": "ws",
            "type": "none",
        }
        vmess = base64.b64encode(json.dumps(vmess_payload).encode()).decode()

        # Test parse normal with protocol-valid, publicly routable fixtures.
        content = (f"vless://{user_id}@vless.example.com:443?type=tcp#remark\n" f"vmess://{vmess}").encode()
        lines = fmt.parse(content, {})
        self.assertEqual(len(lines), 2)
        self.assertEqual(
            lines[0]["data"]["line"],
            f"vless://{user_id}@vless.example.com:443?type=tcp",
        )

        # Test parse base64
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
        import base64
        import json

        fmt = NpvtSubHandler()
        self.assertEqual(fmt.format_id, "npvtsub")

        user_id = "33333333-3333-4333-8333-333333333333"
        vmess_payload = {
            "v": "2",
            "add": "vmess-sub.example.com",
            "port": "443",
            "id": "44444444-4444-4444-8444-444444444444",
            "aid": "0",
            "net": "ws",
            "type": "none",
        }
        vmess = base64.b64encode(json.dumps(vmess_payload).encode()).decode()
        content = (f"vless://{user_id}@vless-sub.example.com:443#tag\n" f"vmess://{vmess}\n" "garbage").encode()
        records = fmt.parse(content, {})
        self.assertEqual(len(records), 2)
        self.assertEqual(
            records[0]["data"]["line"],
            f"vless://{user_id}@vless-sub.example.com:443",
        )

        # Test base64 decode path
        plain = (f"vless://{user_id}@vless-sub.example.com:443\n" "trojan://secret@trojan-sub.example.com:443").encode()
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

    def _assert_opaque_bundle_round_trip(self, handler_class, payload, filename):
        """Every opaque format republishes the source blob inside a ZIP."""
        mock_store = MagicMock()
        mock_store.get.return_value = payload
        handler = handler_class(mock_store)
        parsed = handler.parse(payload, {"filename": filename})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["data"]["filename"], filename)

        built = handler.build(parsed)
        self.assertTrue(built.startswith(b"PK"))
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(built)) as zf:
            self.assertEqual(zf.read(filename), payload)

    def test_ovpn_handler(self):
        self.assertEqual(OvpnHandler(MagicMock()).format_id, "ovpn")
        self._assert_opaque_bundle_round_trip(OvpnHandler, b"ovpn-config", "tunnel.ovpn")

    def test_dark_handler(self):
        self.assertEqual(DarkHandler(MagicMock()).format_id, "dark")
        self._assert_opaque_bundle_round_trip(DarkHandler, b"dark-config", "tunnel.dark")

    def test_nm_handler(self):
        self.assertEqual(NmHandler(MagicMock()).format_id, "nm")
        self._assert_opaque_bundle_round_trip(NmHandler, b"nm-config", "tunnel.nm")

    def test_npv4_handler(self):
        # No decryption credential is configured here, so the blob is
        # preserved verbatim: the encrypted source stays canonical.
        self.assertEqual(Npv4Handler(MagicMock()).format_id, "npv4")
        self._assert_opaque_bundle_round_trip(Npv4Handler, b"npv4-config", "tunnel.npv4")

    def test_tut_sks_tmt_handlers(self):
        for handler, suffix in (
            (TutHandler, ".tut"),
            (SksHandler, ".sks"),
            (TmtHandler, ".tmt"),
        ):
            with self.subTest(format=suffix.lstrip(".")):
                self.assertEqual(handler(MagicMock()).format_id, suffix.lstrip("."))
                self._assert_opaque_bundle_round_trip(
                    handler, ("payload" + suffix).encode(), "tunnel" + suffix
                )

    def test_slipnet_handler(self):
        fmt = SlipNetHandler()
        self.assertEqual(fmt.format_id, "slipnet")

        # An undecryptable link is still a record: the encrypted form is
        # the canonical artifact when no credential is configured.
        link = "slipnet-enc://dGVzdA==-abc123"
        parsed = fmt.parse(link.encode(), {})
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["data"]["line"], link)

        built = fmt.build(parsed)
        self.assertEqual(built.decode("utf-8"), link + "\n")

    def test_malformed_payload_handling(self):
        # NPVT malformed Base64 handling
        fmt_npvt = NpvtHandler()
        corrupt_b64 = b"!!!NotValidBase64!!!"
        parsed_corrupt = fmt_npvt.parse(corrupt_b64, {})
        self.assertEqual(len(parsed_corrupt), 0)

        # ConfLines empty & all-comment handling
        fmt_conf = ConfLinesHandler()
        empty_conf = b"# Only comments\n# Another comment\n\n"
        self.assertEqual(len(fmt_conf.parse(empty_conf, {})), 0)

        # NPVTSub malformed lines handling
        fmt_sub = NpvtSubHandler()
        mixed_corrupt = b"invalid_protocol://bad@url\n\n  \n"
        self.assertEqual(len(fmt_sub.parse(mixed_corrupt, {})), 0)
