import unittest
from mergebot.core.router import decide_format


class TestRouter(unittest.TestCase):
    def test_extension_based(self):
        self.assertEqual(decide_format("test.ovpn", b""), "ovpn")
        self.assertEqual(decide_format("TEST.OVPN", b""), "ovpn")
        self.assertEqual(decide_format("config.npv4", b""), "npv4")
        self.assertEqual(decide_format("something.conf", b""), "conf_lines")

    def test_extension_ehi(self):
        self.assertEqual(decide_format("tunnel.ehi", b""), "ehi")
        self.assertEqual(decide_format("TUNNEL.EHI", b""), "ehi")

    def test_extension_hc(self):
        self.assertEqual(decide_format("config.hc", b""), "hc")
        self.assertEqual(decide_format("CONFIG.HC", b""), "hc")

    def test_extension_hat(self):
        self.assertEqual(decide_format("proxy.hat", b""), "hat")
        self.assertEqual(decide_format("PROXY.HAT", b""), "hat")

    def test_extension_sip(self):
        self.assertEqual(decide_format("account.sip", b""), "sip")
        self.assertEqual(decide_format("ACCOUNT.SIP", b""), "sip")

    def test_extension_npvtsub(self):
        self.assertEqual(decide_format("sub.npvtsub", b""), "npvtsub")
        self.assertEqual(decide_format("SUB.NPVTSUB", b""), "npvtsub")

    def test_content_based_npvt(self):
        content = b"vless://uuid@host:port"
        self.assertEqual(decide_format("file.txt", content), "npvt")

        content = b"vmess://base64"
        self.assertEqual(decide_format("file", content), "npvt")

        content = b"trojan://password@host:port"
        self.assertEqual(decide_format("unknown", content), "npvt")

    def test_fallback_opaque(self):
        self.assertEqual(decide_format("random.bin", b"\x00\x01"), "opaque_bundle")
        self.assertEqual(decide_format("text.txt", b"Hello World"), "opaque_bundle")

    def test_decide_format_utf8_error(self):
        # Invalid utf-8 sequence that cannot be decoded
        content = b"\xff\xff\xff"
        # Should fall back to opaque_bundle
        self.assertEqual(decide_format("test.txt", content), "opaque_bundle")
