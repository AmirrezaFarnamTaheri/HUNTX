"""Tests for proxy URI remark stripping and deduplication."""
import base64
import json
import unittest
from huntx.formats.npvt import (
    NpvtHandler,
    strip_proxy_remark,
    add_clean_remark,
)
from huntx.formats.npvtsub import NpvtSubHandler


class TestStripProxyRemark(unittest.TestCase):
    """Test strip_proxy_remark removes #fragment / vmess ps field."""

    def test_strip_vless_fragment(self):
        uri = "vless://uuid@1.2.3.4:443?type=tcp#MyChannel"
        self.assertEqual(strip_proxy_remark(uri), "vless://uuid@1.2.3.4:443?type=tcp")

    def test_strip_trojan_fragment(self):
        uri = "trojan://pass@host:443#ChannelName"
        self.assertEqual(strip_proxy_remark(uri), "trojan://pass@host:443")

    def test_strip_ss_fragment(self):
        uri = "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ@1.2.3.4:8388#Server1"
        self.assertEqual(strip_proxy_remark(uri), "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ@1.2.3.4:8388")

    def test_strip_hysteria2_fragment(self):
        uri = "hysteria2://pass@host:443?sni=example.com#FreeProxy"
        self.assertEqual(strip_proxy_remark(uri), "hysteria2://pass@host:443?sni=example.com")

    def test_no_fragment_unchanged(self):
        uri = "vless://uuid@1.2.3.4:443?type=tcp"
        self.assertEqual(strip_proxy_remark(uri), uri)

    def test_strip_vmess_ps_field(self):
        obj = {"v": "2", "ps": "ChannelXYZ", "add": "1.2.3.4", "port": "443",
               "id": "uuid", "aid": "0", "net": "ws", "type": "none"}
        b64 = base64.b64encode(json.dumps(obj).encode()).decode()
        uri = f"vmess://{b64}"

        stripped = strip_proxy_remark(uri)

        # Decode the stripped vmess to verify ps is gone
        inner_b64 = stripped[8:]
        padding = 4 - len(inner_b64) % 4
        if padding != 4:
            inner_b64 += "=" * padding
        decoded = json.loads(base64.b64decode(inner_b64).decode())
        self.assertNotIn("ps", decoded)
        self.assertEqual(decoded["add"], "1.2.3.4")
        self.assertEqual(decoded["id"], "uuid")

    def test_vmess_same_proxy_different_remark_dedup(self):
        """Two vmess URIs differing only in ps field should strip to the same string."""
        base = {"v": "2", "add": "1.2.3.4", "port": "443", "id": "uuid",
                "aid": "0", "net": "ws", "type": "none"}

        obj1 = {**base, "ps": "Channel_A"}
        obj2 = {**base, "ps": "Channel_B_Free"}

        uri1 = "vmess://" + base64.b64encode(json.dumps(obj1).encode()).decode()
        uri2 = "vmess://" + base64.b64encode(json.dumps(obj2).encode()).decode()

        self.assertNotEqual(uri1, uri2)
        self.assertEqual(strip_proxy_remark(uri1), strip_proxy_remark(uri2))

    def test_standard_uri_same_proxy_different_remark_dedup(self):
        """Two vless URIs differing only in #remark should strip to the same string."""
        uri1 = "vless://uuid@1.2.3.4:443?type=tcp#Channel_A"
        uri2 = "vless://uuid@1.2.3.4:443?type=tcp#Channel_B"

        self.assertNotEqual(uri1, uri2)
        self.assertEqual(strip_proxy_remark(uri1), strip_proxy_remark(uri2))


class TestAddCleanRemark(unittest.TestCase):
    """Test add_clean_remark assigns protocol-N tags."""

    def test_vless_remark(self):
        counter = {}
        result = add_clean_remark("vless://uuid@host:443", counter)
        self.assertEqual(result, "vless://uuid@host:443#vless-1")
        self.assertEqual(counter, {"vless": 1})

    def test_trojan_sequential(self):
        counter = {}
        r1 = add_clean_remark("trojan://a@h:443", counter)
        r2 = add_clean_remark("trojan://b@h:443", counter)
        self.assertIn("#trojan-1", r1)
        self.assertIn("#trojan-2", r2)

    def test_vmess_remark(self):
        obj = {"v": "2", "add": "1.2.3.4", "port": "443", "id": "uuid"}
        b64 = base64.b64encode(json.dumps(obj).encode()).decode()
        uri = f"vmess://{b64}"
        counter = {}
        result = add_clean_remark(uri, counter)

        # Decode the result to check ps field
        inner_b64 = result[8:]
        padding = 4 - len(inner_b64) % 4
        if padding != 4:
            inner_b64 += "=" * padding
        decoded = json.loads(base64.b64decode(inner_b64).decode())
        self.assertEqual(decoded["ps"], "vmess-1")

    def test_mixed_protocols(self):
        counter = {}
        add_clean_remark("vless://a@h:1", counter)
        add_clean_remark("trojan://b@h:2", counter)
        add_clean_remark("vless://c@h:3", counter)
        self.assertEqual(counter, {"vless": 2, "trojan": 1})


class TestNpvtDedup(unittest.TestCase):
    """Test that NpvtHandler deduplicates same-proxy-different-remark URIs."""

    def test_same_vless_different_remarks_deduped(self):
        handler = NpvtHandler()
        content = (
            "vless://uuid@1.2.3.4:443?type=tcp#Channel_A\n"
            "vless://uuid@1.2.3.4:443?type=tcp#Channel_B\n"
            "vless://uuid@1.2.3.4:443?type=tcp#Channel_C\n"
        ).encode()

        records = handler.parse(content, {})
        self.assertEqual(len(records), 1)

    def test_same_vmess_different_ps_deduped(self):
        handler = NpvtHandler()
        base = {"v": "2", "add": "1.2.3.4", "port": "443", "id": "uuid",
                "aid": "0", "net": "ws", "type": "none"}

        lines = []
        for name in ["Channel_A", "Channel_B", "Channel_C"]:
            obj = {**base, "ps": name}
            b64 = base64.b64encode(json.dumps(obj).encode()).decode()
            lines.append(f"vmess://{b64}")

        content = "\n".join(lines).encode()
        records = handler.parse(content, {})
        self.assertEqual(len(records), 1)

    def test_different_proxies_not_deduped(self):
        handler = NpvtHandler()
        content = (
            "vless://uuid1@1.2.3.4:443#A\n"
            "vless://uuid2@5.6.7.8:443#A\n"
        ).encode()
        records = handler.parse(content, {})
        self.assertEqual(len(records), 2)

    def test_build_adds_clean_remarks(self):
        handler = NpvtHandler()
        content = (
            "vless://a@1.2.3.4:443#Old_Remark\n"
            "trojan://b@5.6.7.8:443#Another_Remark\n"
        ).encode()
        records = handler.parse(content, {})
        built = handler.build(records).decode()
        lines = built.strip().split("\n")
        self.assertEqual(len(lines), 2)
        self.assertIn("#vless-1", lines[0])
        self.assertIn("#trojan-1", lines[1])

    def test_build_deduplicates_again(self):
        """Build should also deduplicate if records from different sources
        happen to contain the same proxy."""
        handler = NpvtHandler()
        records = [
            {"data": {"line": "vless://uuid@host:443"}},
            {"data": {"line": "vless://uuid@host:443"}},
        ]
        built = handler.build(records).decode()
        lines = [l for l in built.strip().split("\n") if l]
        self.assertEqual(len(lines), 1)


class TestNpvtSubDedup(unittest.TestCase):
    """Test that NpvtSubHandler also deduplicates same-proxy-different-remark."""

    def test_same_proxy_different_remarks_deduped(self):
        handler = NpvtSubHandler()
        content = (
            "trojan://pass@host:443#Channel_X\n"
            "trojan://pass@host:443#Channel_Y\n"
        ).encode()
        records = handler.parse(content, {})
        self.assertEqual(len(records), 1)


if __name__ == "__main__":
    unittest.main()
