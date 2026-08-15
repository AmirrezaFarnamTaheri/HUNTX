import base64
import json
import unittest
from unittest.mock import Mock

from huntx.formats.common.singbox import (
    TARGET_SINGBOX_VERSION,
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

    def test_parse_trojan_hysteria2_and_shadowsocks(self):
        trojan = parse_proxy_uri("trojan://secret@t.example.com:443?sni=t.example.com#T")
        self.assertEqual(trojan.type, "trojan")
        self.assertEqual(trojan.password, "secret")

        hy2 = parse_proxy_uri(
            "hysteria2://pw@h.example.com:8443?sni=h.example.com"
            "&obfs=salamander&obfs-password=obfs-secret#H"
        )
        self.assertEqual(hy2.type, "hysteria2")
        self.assertEqual(hy2.password, "pw")
        self.assertEqual(hy2.obfs_type, "salamander")
        self.assertEqual(hy2.obfs_password, "obfs-secret")

        userinfo = base64.b64encode(b"aes-256-gcm:password123").decode()
        ss = parse_proxy_uri(f"ss://{userinfo}@s.example.com:8388#SS")
        self.assertIsNotNone(ss)
        self.assertEqual(ss.type, "shadowsocks")
        self.assertEqual(ss.method, "aes-256-gcm")
        self.assertEqual(ss.password, "password123")

    def test_hysteria2_does_not_alias_obfs_type_to_password(self):
        node = parse_proxy_uri("hy2://pw@h.example.com:8443?obfs=salamander#H")
        self.assertEqual(node.obfs_type, "salamander")
        self.assertEqual(node.obfs_password, "")
        config = config_from_uris(["hy2://pw@h.example.com:8443?obfs=salamander#H"])
        outbound = next(item for item in config["outbounds"] if item.get("type") == "hysteria2")
        self.assertNotIn("obfs", outbound)

    def test_hysteria2_port_range_is_rendered_in_current_syntax(self):
        node = parse_proxy_uri(
            "hysteria2://pw@h2.example.com:8443?sni=h2.example.com"
            "&up_mbps=80&down_mbps=200&mport=20000-30000#H2"
        )
        self.assertEqual(node.server_ports, ["20000-30000"])
        config = config_from_uris(
            ["hysteria2://pw@h2.example.com:8443?sni=h2.example.com&mport=20000-30000#H2"]
        )
        outbound = next(item for item in config["outbounds"] if item.get("type") == "hysteria2")
        self.assertEqual(outbound["server_ports"], ["20000:30000"])
        self.assertNotIn("server_port", outbound)

    def test_current_renderer_skips_removed_legacy_native_outbounds(self):
        self.assertEqual(TARGET_SINGBOX_VERSION, "1.14+")
        self.assertIsNone(parse_proxy_uri("hysteria://h1.example.com:443?auth=secret#H1"))
        self.assertIsNone(parse_proxy_uri("wireguard://legacy"))

    def test_anytls_and_double_encoded_tag(self):
        node = parse_proxy_uri("anytls://pass123@a.example.com:8443?sni=a.example.com&insecure=1#A")
        self.assertIsNotNone(node)
        self.assertEqual(node.type, "anytls")
        self.assertTrue(node.tls_enabled)
        self.assertTrue(node.tls_insecure)

        tagged = parse_proxy_uri("trojan://secret@t.example.com:443?sni=t.example.com#My%2520Node")
        self.assertEqual(tagged.tag, "My Node")

    def test_unknown_scheme_returns_none(self):
        self.assertIsNone(parse_proxy_uri("http://not-a-proxy"))
        self.assertIsNone(parse_proxy_uri("garbage"))


class TestSingboxConfig(unittest.TestCase):
    def test_config_uses_current_schema_and_no_removed_special_outbounds(self):
        config = config_from_uris(["trojan://secret@t.example.com:443?sni=t.example.com#Node"])
        self.assertEqual(config["route"]["final"], "select")
        self.assertEqual(config["route"]["default_domain_resolver"], "google")
        self.assertTrue(config["dns"]["optimistic"])
        self.assertTrue(all("type" in server for server in config["dns"]["servers"]))
        self.assertTrue(all("address" not in server for server in config["dns"]["servers"]))

        outbound_types = {item["type"] for item in config["outbounds"]}
        self.assertIn("selector", outbound_types)
        self.assertIn("urltest", outbound_types)
        self.assertIn("direct", outbound_types)
        self.assertTrue(outbound_types.isdisjoint({"block", "dns", "wireguard", "hysteria"}))

        trojan = next(item for item in config["outbounds"] if item.get("type") == "trojan")
        self.assertEqual(trojan["domain_resolver"], "google")

    def test_reserved_and_duplicate_tags_are_renamed(self):
        config = config_from_uris(
            [
                "trojan://secret@t.example.com:443?sni=t.example.com#auto",
                "trojan://secret@t.example.com:443?sni=t.example.com#direct",
                "trojan://secret@t.example.com:443?sni=t.example.com#Node",
                "trojan://secret@t.example.com:443?sni=t.example.com#Node",
            ]
        )
        tags = [item["tag"] for item in config["outbounds"]]
        self.assertEqual(len(tags), len(set(tags)))
        proxy_tags = [item["tag"] for item in config["outbounds"] if item.get("type") == "trojan"]
        self.assertIn("auto-1", proxy_tags)
        self.assertIn("direct-1", proxy_tags)
        self.assertIn("Node", proxy_tags)
        self.assertIn("Node-1", proxy_tags)

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

        formats = {result["format"] for result in results}
        self.assertIn("npvt", formats)
        self.assertIn("npvt.decoded.json", formats)
        self.assertIn("npvt.b64sub", formats)
        self.assertIn("npvt.singbox.json", formats)

        saved_formats = {call.args[1] for call in self.artifact_store.save_output.call_args_list}
        self.assertIn("npvt.singbox.json", saved_formats)

        singbox_result = next(result for result in results if result["format"] == "npvt.singbox.json")
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
        formats = {result["format"] for result in results}
        self.assertNotIn("npvt.singbox.json", formats)


if __name__ == "__main__":
    unittest.main()
