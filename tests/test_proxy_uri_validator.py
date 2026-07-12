import base64
import json
import unittest

from huntx.formats.proxy_uri_validator import validate_proxy_uri


def _b64(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


class TestAcceptedProxyUris(unittest.TestCase):
    def test_plaintext_sip002(self) -> None:
        self.assertTrue(
            validate_proxy_uri(
                "ss://chacha20-ietf-poly1305:secret@example.com:443#node"
            )
        )

    def test_encoded_userinfo_sip002(self) -> None:
        userinfo = _b64("aes-256-gcm:secret")
        self.assertTrue(validate_proxy_uri(f"ss://{userinfo}@example.com:8443"))

    def test_legacy_encoded_sip002(self) -> None:
        payload = _b64("aes-128-gcm:secret@example.com:9443")
        self.assertTrue(validate_proxy_uri(f"ss://{payload}"))

    def test_sip002_plugin_is_preserved_as_a_valid_extension(self) -> None:
        self.assertTrue(
            validate_proxy_uri(
                "ss://aes-256-gcm:secret@example.com:443?plugin=v2ray-plugin%3Btls"
            )
        )

    def test_ssr(self) -> None:
        password = _b64("secret")
        payload = _b64(f"example.com:443:origin:aes-256-cfb:plain:{password}/?")
        self.assertTrue(validate_proxy_uri(f"ssr://{payload}"))

    def test_vmess(self) -> None:
        payload = _b64(
            json.dumps(
                {
                    "v": "2",
                    "ps": "fixture",
                    "add": "example.com",
                    "port": "443",
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "aid": "0",
                    "net": "ws",
                    "type": "none",
                    "host": "example.com",
                    "path": "/ws",
                    "tls": "tls",
                }
            )
        )
        self.assertTrue(validate_proxy_uri(f"vmess://{payload}"))

    def test_vless_reality(self) -> None:
        self.assertTrue(
            validate_proxy_uri(
                "vless://123e4567-e89b-12d3-a456-426614174000@example.com:443"
                "?security=reality&pbk=public-key&sni=example.com"
            )
        )

    def test_trojan(self) -> None:
        self.assertTrue(validate_proxy_uri("trojan://secret@example.com:443?security=tls"))

    def test_hysteria2_with_obfuscation_pair(self) -> None:
        self.assertTrue(
            validate_proxy_uri(
                "hysteria2://secret@example.com:443?obfs=salamander&obfs-password=cover"
            )
        )

    def test_hysteria2_without_obfuscation(self) -> None:
        self.assertTrue(validate_proxy_uri("hy2://secret@example.com:443"))

    def test_tuic(self) -> None:
        self.assertTrue(validate_proxy_uri("tuic://secret@example.com:443"))

    def test_generic_known_endpoint_schemes(self) -> None:
        fixtures = (
            "hysteria://secret@example.com:443",
            "wireguard://secret@example.com:51820",
            "wg://secret@example.com:51820",
            "socks://example.com:1080",
            "socks4://example.com:1080",
            "socks5://example.com:1080",
            "anytls://secret@example.com:443",
            "juicity://secret@example.com:443",
            "warp://example.com:2408",
            "dns://example.com:53",
            "dnstt://example.com:53",
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.assertTrue(validate_proxy_uri(fixture))


class TestRejectedProxyUris(unittest.TestCase):
    def test_empty_whitespace_multiline_and_trailing_prose(self) -> None:
        fixtures = (
            "",
            " trojan://secret@example.com:443",
            "trojan://secret@example.com:443 ",
            "trojan://secret@example.com:443\nsecond-line",
            "trojan://secret@example.com:443 trailing",
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.assertFalse(validate_proxy_uri(fixture))

    def test_unknown_scheme_is_rejected(self) -> None:
        self.assertFalse(validate_proxy_uri("unknown://secret@example.com:443"))

    def test_private_local_reserved_and_unspecified_literals_are_rejected(self) -> None:
        fixtures = (
            "trojan://secret@127.0.0.1:443",
            "trojan://secret@10.0.0.1:443",
            "trojan://secret@169.254.1.1:443",
            "trojan://secret@0.0.0.0:443",
            "trojan://secret@192.0.2.1:443",
            "trojan://secret@[::1]:443",
            "trojan://secret@[::]:443",
            "trojan://secret@localhost:443",
            "trojan://secret@service.local:443",
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.assertFalse(validate_proxy_uri(fixture))

    def test_invalid_or_missing_port(self) -> None:
        fixtures = (
            "trojan://secret@example.com",
            "trojan://secret@example.com:0",
            "trojan://secret@example.com:65536",
            "trojan://secret@example.com:not-a-port",
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.assertFalse(validate_proxy_uri(fixture))

    def test_invalid_vless_identity_and_reality_fields(self) -> None:
        fixtures = (
            "vless://not-a-uuid@example.com:443",
            "vless://123e4567-e89b-12d3-a456-426614174000@example.com:443?security=reality",
            "vless://123e4567-e89b-12d3-a456-426614174000@example.com:443?security=reality&pbk=key",
            "vless://123e4567-e89b-12d3-a456-426614174000@example.com:443?security=reality&sni=example.com",
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.assertFalse(validate_proxy_uri(fixture))

    def test_hysteria2_requires_complete_obfuscation_pair(self) -> None:
        self.assertFalse(
            validate_proxy_uri("hysteria2://secret@example.com:443?obfs=salamander")
        )
        self.assertFalse(
            validate_proxy_uri("hysteria2://secret@example.com:443?obfs-password=cover")
        )

    def test_authentication_required_protocols_reject_empty_identity(self) -> None:
        fixtures = (
            "trojan://example.com:443",
            "hysteria2://example.com:443",
            "tuic://example.com:443",
            "wireguard://example.com:51820",
            "anytls://example.com:443",
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.assertFalse(validate_proxy_uri(fixture))

    def test_malformed_vmess_and_shadowsocks_are_rejected(self) -> None:
        fixtures = (
            "vmess://not-base64",
            f"vmess://{_b64('{}')}",
            "ss://not-base64",
            "ss://unknown-method:secret@example.com:443",
            "ss://aes-256-gcm:@example.com:443",
            "ss://aes-256-gcm:secret@example.com:443?plugin=",
            "ssr://not-base64",
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.assertFalse(validate_proxy_uri(fixture))


if __name__ == "__main__":
    unittest.main()
