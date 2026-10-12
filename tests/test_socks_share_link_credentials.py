"""SOCKS share links carry their credentials in two shapes; both must survive.

Publishers emit SOCKS links either as a literal ``user:pass`` pair or as that
same pair base64-encoded into a single opaque token. Splitting only on a
literal colon sent the whole encoded blob through as the username and left the
password empty, so the node could never authenticate and the emitted sing-box
outbound named a user with no password at all.
"""

import base64
import json
import unittest

from huntx.formats.common.nekobox import build_nekobox_outbounds_bytes
from huntx.formats.common.singbox import config_from_uris, parse_proxy_uri


def _encoded(user: str, password: str) -> str:
    return base64.b64encode(f"{user}:{password}".encode()).decode()


class TestSocksShareLinkCredentials(unittest.TestCase):
    def test_base64_userinfo_splits_into_username_and_password(self):
        node = parse_proxy_uri(f"socks://{_encoded('111', '111')}@198.51.100.1:11310#socks-1")
        self.assertIsNotNone(node)
        self.assertEqual(node.type, "socks")
        self.assertEqual(node.username, "111")
        self.assertEqual(node.password, "111")

    def test_base64_userinfo_keeps_colons_inside_the_password(self):
        node = parse_proxy_uri(
            f"socks://{_encoded('KH6JSw8m', 'V2RayyNGvpn-V2RayyNGvpn')}@198.51.100.2:8443#socks-2"
        )
        self.assertEqual(node.username, "KH6JSw8m")
        self.assertEqual(node.password, "V2RayyNGvpn-V2RayyNGvpn")

    def test_literal_userinfo_is_unchanged(self):
        node = parse_proxy_uri("socks5://alice:hunter2@198.51.100.3:1080#socks5")
        self.assertEqual(node.username, "alice")
        self.assertEqual(node.password, "hunter2")

    def test_credential_free_link_stays_credential_free(self):
        node = parse_proxy_uri("socks5://198.51.100.4:1080#open")
        self.assertEqual(node.username, "")
        self.assertEqual(node.password, "")

    def test_undecodable_userinfo_is_preserved_verbatim(self):
        node = parse_proxy_uri("socks5://not base64 at all@198.51.100.5:1080#odd")
        self.assertEqual(node.username, "not base64 at all")
        self.assertEqual(node.password, "")

    def test_emitted_outbound_pairs_the_username_with_its_password(self):
        config = config_from_uris(
            [f"socks://{_encoded('111', '111')}@198.51.100.1:11310#socks-1"]
        )
        outbound = next(item for item in config["outbounds"] if item.get("type") == "socks")
        self.assertEqual(outbound["username"], "111")
        self.assertEqual(outbound["password"], "111")

    def test_nekobox_feed_pairs_the_username_with_its_password(self):
        payload = build_nekobox_outbounds_bytes(
            f"socks://{_encoded('123', '123')}@198.51.100.6:3060#socks-3"
        )
        outbound = json.loads(payload)[0]
        self.assertEqual(outbound["username"], "123")
        self.assertEqual(outbound["password"], "123")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
