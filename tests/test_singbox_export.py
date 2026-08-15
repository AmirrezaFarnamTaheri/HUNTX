import json
import unittest
from unittest.mock import Mock

from huntx.formats.common.singbox import (
    build_singbox_config_bytes,
    config_from_uris,
    parse_proxy_uri,
)
from huntx.pipeline.build import BuildPipeline


class TestSingboxParsing(unittest.TestCase):
    def test_parse_vless_reality(self):
        uri = (
            "vless://11111111-2222-3333-4444-555555555555@example.com:443"
            "?security=reality&pbk=PUBKEY&sid=ab12&sni=cdn.example.com&flow=xtls-rprx-vision"
            "&type=grpc&serviceName=grpcsvc#My%20Node"
        )
        node = parse_proxy_uri(uri)
        self.assertIsNotNone(node)
        self.assertEqual(node.type, "vless")
        self.assertEqual(node.server, "example.com")
        self.assertEqual(node.port, 443)
        self.assertEqual(node.tag, "My Node")
        self.assertTrue(node.tls_reality_enabled)
        self.assertEqual(node.tls_reality_public_key, "PUBKEY")
        self.assertEqual(node.flow, "xtls-rprx-vision")
        self.assertEqual(node.transport_type, "grpc")
        self.assertEqual(node.transport_service_name, "grpcsvc")

    def test_parse_vmess_ws(self):
        import base64

        payload = {
            "v": "2",
            "ps": "vmess-node",
            "add": "1.2.3.4",
            "port": "8080",
            "id": "uuid-here",
            "aid": "0",
            "net": "ws",
            "path": "/ws",
            "host": "cdn.example.com",
            "tls": "tls",
        }
        raw = base64.b64encode(json.dumps(payload).encode()).decode()
        node = parse_proxy_uri(f"vmess://{raw}")
        self.assertIsNotNone(node)
        self.assertEqual(node.type, "vmess")
        self.assertEqual(node.server, "1.2.3.4")
        self.assertEqual(node.port, 8080)
        self.assertEqual(node.transport_type, "ws")
        self.assertEqual(node.transport_path, "/ws")
        self.assertTrue(node.tls_enabled)

    def test_parse_trojan_and_hysteria2(self):
        trojan = parse_proxy_uri("trojan://secret@t.example.com:443?sni=t.example.com#T")
        self.assertEqual(trojan.type, "trojan")
        self.assertEqual(trojan.password, "secret")
        hy2 = parse_proxy_uri("hysteria2://pw@h.example.com:8443?sni=h.example.com&obfs=salamander#H")
        self.assertEqual(hy2.type, "hysteria2")
        self.assertEqual(hy2.password, "pw")

    def test_parse_ss_base64_userinfo(self):
        import base64

        userinfo = base64.b64encode(b"aes-256-gcm:password123").decode()
        node = parse_proxy_uri(f"ss://{userinfo}@s.example.com:8388#SS")
        self.assertIsNotNone(node)
        self.assertEqual(node.type, "shadowsocks")
        self.assertEqual(node.method, "aes-256-gcm")
        self.assertEqual(node.password, "password123")
        self.assertEqual(node.port, 8388)

    def test_unknown_scheme_returns_none(self):
        self.assertIsNone(parse_proxy_uri("http://not-a-proxy"))
        self.assertIsNone(parse_proxy_uri("garbage"))

    def test_parse_ss_json_userinfo(self):
        import base64

        payload = json.dumps(
            {
                "server": "j.example.com",
                "server_port": 8388,
                "method": "chacha20-ietf-poly1305",
                "password": "pw",
            }
        )
        raw = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
        node = parse_proxy_uri(f"ss://{raw}")
        self.assertIsNotNone(node)
        self.assertEqual(node.type, "shadowsocks")
        self.assertEqual(node.server, "j.example.com")
        self.assertEqual(node.port, 8388)
        self.assertEqual(node.method, "chacha20-ietf-poly1305")

    def test_parse_hysteria_v1(self):
        node = parse_proxy_uri(
            "hysteria://h1.example.com:443?auth=secret&peer=sni.example.com" "&up_mbps=50&down_mbps=100&obfs=xplus#H1"
        )
        self.assertIsNotNone(node)
        self.assertEqual(node.type, "hysteria")
        self.assertEqual(node.server, "h1.example.com")
        self.assertEqual(node.password, "secret")
        self.assertEqual(node.up_mbps, 50)
        self.assertEqual(node.down_mbps, 100)
        self.assertEqual(node.obfs_password, "xplus")

    def test_parse_hysteria2_bandwidth_and_ports(self):
        node = parse_proxy_uri(
            "hysteria2://pw@h2.example.com:8443?sni=h2.example.com" "&up_mbps=80&down_mbps=200&mport=20000-30000#H2"
        )
        self.assertEqual(node.type, "hysteria2")
        self.assertEqual(node.up_mbps, 80)
        self.assertEqual(node.down_mbps, 200)
        self.assertEqual(node.server_ports, ["20000-30000"])

    def test_parse_anytls(self):
        node = parse_proxy_uri("anytls://pass123@a.example.com:8443?sni=a.example.com&insecure=1#A")
        self.assertIsNotNone(node)
        self.assertEqual(node.type, "anytls")
        self.assertEqual(node.server, "a.example.com")
        self.assertEqual(node.port, 8443)
        self.assertEqual(node.password, "pass123")
        self.assertTrue(node.tls_enabled)
        self.assertTrue(node.tls_insecure)

    def test_anytls_outbound_and_juicity_skip(self):
        cfg = config_from_uris(["anytls://pw@a.example.com:8443?sni=a.example.com#A"])
        anytls = [ob for ob in cfg["outbounds"] if ob.get("type") == "anytls"]
        self.assertEqual(len(anytls), 1)
        self.assertEqual(anytls[0]["password"], "pw")
        self.assertIn("tls", anytls[0])
        # juicity has no native sing-box outbound type → not converted.
        self.assertIsNone(parse_proxy_uri("juicity://uuid:pw@j.example.com:443#J"))

    def test_double_encoded_tag_is_fully_unquoted(self):
        # %2520 -> %20 -> space; single-pass unquote would stop at "%20".
        node = parse_proxy_uri("trojan://secret@t.example.com:443?sni=t.example.com#My%2520Node")
        self.assertIsNotNone(node)
        self.assertEqual(node.tag, "My Node")


class TestSingboxConfig(unittest.TestCase):
    def test_config_from_uris_structure(self):
        config = config_from_uris(
            [
                "trojan://secret@t.example.com:443?sni=t.example.com#Node",
                "trojan://secret@t.example.com:443?sni=t.example.com#Node",  # dup tag
            ]
        )
        tags = [ob["tag"] for ob in config["outbounds"] if ob.get("type") == "trojan"]
        self.assertEqual(len(tags), 2)
        self.assertEqual(len(set(tags)), 2)  # de-duplicated tags
        outbound_types = {ob["type"] for ob in config["outbounds"]}
        self.assertIn("selector", outbound_types)
        self.assertIn("urltest", outbound_types)
        self.assertIn("direct", outbound_types)
        self.assertEqual(config["route"]["final"], "select")
        self.assertIn("experimental", config)
        self.assertTrue(config["dns"].get("optimistic"))

    def test_build_bytes_empty_when_no_proxies(self):
        self.assertEqual(build_singbox_config_bytes("just some text\nno uris"), b"")
        self.assertEqual(build_singbox_config_bytes(""), b"")

    def test_build_bytes_valid_json(self):
        raw = build_singbox_config_bytes("trojan://secret@t.example.com:443?sni=t.example.com#Node")
        self.assertTrue(raw)
        parsed = json.loads(raw.decode("utf-8"))
        self.assertIn("outbounds", parsed)
        self.assertIn("inbounds", parsed)


class TestBuildPipelineSingboxDerivative(unittest.TestCase):
    def setUp(self):
        self.state_repo = Mock()
        self.artifact_store = Mock()
        self.registry = Mock()
        self.pipeline = BuildPipeline(self.state_repo, self.artifact_store, self.registry)

    def test_singbox_derivative_emitted_for_proxy_format(self):
        route_config = {"name": "route1", "formats": ["npvt"], "from_sources": ["src1"]}
        proxy_text = b"trojan://secret@t.example.com:443?sni=t.example.com#Node\n"
        self.state_repo.get_records_for_build.return_value = [{"record_type": "npvt", "data": "x"}]
        handler = Mock()
        handler.build.return_value = proxy_text
        self.registry.get.return_value = handler
        self.artifact_store.save_artifact.return_value = "hash"

        results = self.pipeline.run(route_config)

        formats = {r["format"] for r in results}
        self.assertIn("npvt", formats)
        self.assertIn("npvt.decoded.json", formats)
        self.assertIn("npvt.b64sub", formats)
        self.assertIn("npvt.singbox.json", formats)

        saved_formats = {call.args[1] for call in self.artifact_store.save_output.call_args_list}
        self.assertIn("npvt.singbox.json", saved_formats)

        singbox_result = next(r for r in results if r["format"] == "npvt.singbox.json")
        parsed = json.loads(singbox_result["data"].decode("utf-8"))
        self.assertIn("outbounds", parsed)

    def test_no_singbox_derivative_when_no_parseable_uris(self):
        route_config = {"name": "route1", "formats": ["npvt"], "from_sources": ["src1"]}
        self.state_repo.get_records_for_build.return_value = [{"record_type": "npvt", "data": "x"}]
        handler = Mock()
        handler.build.return_value = b"# just a comment\nnot a uri\n"
        self.registry.get.return_value = handler
        self.artifact_store.save_artifact.return_value = "hash"

        results = self.pipeline.run(route_config)

        formats = {r["format"] for r in results}
        self.assertNotIn("npvt.singbox.json", formats)


if __name__ == "__main__":
    unittest.main()
