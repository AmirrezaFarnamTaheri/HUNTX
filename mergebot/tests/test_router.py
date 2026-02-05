import unittest
from mergebot.core.router import decide_format

class TestRouter(unittest.TestCase):
    def test_known_extension(self):
        self.assertEqual(decide_format("test.ovpn", b"some content"), "ovpn")
        self.assertEqual(decide_format("test.npv4", b"some content"), "npv4")
        self.assertEqual(decide_format("test.conf", b"some content"), "conf_lines")

    def test_content_heuristic(self):
        content = b"vless://abcdefg"
        self.assertEqual(decide_format("unknown.txt", content), "npvt")

    def test_unknown_fallback(self):
        content = b"just random binary junk"
        # This asserts the fix: fallback is "opaque_bundle", not "opaque"
        self.assertEqual(decide_format("unknown.bin", content), "opaque_bundle")

if __name__ == "__main__":
    unittest.main()
