"""Regression tests for the persistent latest-100 URI subscriptions."""
from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Imported after setting the repository source path for direct test execution.
from huntx.formats.latest_subscriptions import (  # noqa: E402
    PROTOCOL_CATEGORIES,
    protocol_for_uri,
    validate_latest_subscriptions,
    write_latest_subscriptions,
)


def _vless(n: int) -> str:
    return (
        f"vless://11111111-1111-4111-8111-111111111111@node{n}.example:443"
        "?encryption=none"
    )


class LatestSubscriptionTests(unittest.TestCase):
    def test_protocol_categories_are_separate_and_include_empty_supported_types(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "latest"
            manifest = {"trojan://p@one.example:443": 1}
            index = write_latest_subscriptions(destination, manifest, "2026-11-21T00:00:00Z")
            self.assertTrue({
                "vless", "vmess", "trojan", "anytls", "hysteria", "hysteria2",
                "socks", "http", "shadowsocks", "shadowsocksr", "tuic",
                "wireguard", "ssh", "shadowtls", "naive", "juicity", "mieru",
                "warp", "dns", "dnstt",
            } <= set(PROTOCOL_CATEGORIES))
            self.assertEqual(set(index["protocols"]), set(PROTOCOL_CATEGORIES))
            self.assertNotIn("others", index["protocols"])
            self.assertTrue((destination / "wireguard.txt").exists())
            self.assertEqual((destination / "wireguard.txt").read_bytes(), b"")
            self.assertEqual((destination / "trojan.txt").read_text().splitlines(), [
                "trojan://p@one.example:443",
            ])
            validate_latest_subscriptions(destination)

    def test_per_type_limit_keeps_newest_even_when_old_records_have_no_ttl(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "latest"
            manifest = {_vless(i): i + 1 for i in range(105)}
            manifest["trojan://password@old.example:443"] = 1
            index = write_latest_subscriptions(destination, manifest, "2026-11-21T00:00:00Z")
            vless = (destination / "vless.txt").read_text().splitlines()
            self.assertEqual(len(vless), 100)
            self.assertEqual(vless[0], _vless(104))
            self.assertEqual(vless[-1], _vless(5))
            self.assertNotIn(_vless(4), vless)
            self.assertEqual((destination / "trojan.txt").read_text().splitlines(),
                             ["trojan://password@old.example:443"])
            self.assertEqual(index["aggregate"]["count"], 101)
            self.assertEqual(len((destination / "all.txt").read_text().splitlines()), 101)
            validate_latest_subscriptions(destination)

    def test_aliases_deduplication_credentials_and_http_safety(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "latest"
            manifest = {
                "hy2://password@same.example:443#first": 3,
                "hysteria2://password@same.example:443#second": 4,
                "socks5://u:p@socks.example:1080": 5,
                "socks4://u:p@socks.example:1080": 6,
                "http://u:p@http.example:8080": 7,
                "https://ordinary.example/articles": 8,
                "trojan://a@same.example:443": 9,
                "trojan://b@same.example:443": 10,
                "javascript://bad.example:443": 11,
            }
            index = write_latest_subscriptions(destination, manifest, "2026-11-21T00:00:00Z")
            self.assertEqual(index["protocols"]["hysteria2"]["count"], 1)
            self.assertFalse((destination / "hy2.txt").exists())
            self.assertEqual(index["protocols"]["socks"]["count"], 2)
            self.assertEqual(index["protocols"]["http"]["count"], 1)
            self.assertEqual(index["protocols"]["trojan"]["count"], 2)
            self.assertEqual(index["aggregate"]["count"], 6)
            self.assertNotIn("others", index["protocols"])
            self.assertIsNone(protocol_for_uri("https://ordinary.example/articles"))
            self.assertIsNone(protocol_for_uri("javascript://bad.example:443"))
            self.assertEqual(protocol_for_uri("hy2://password@same.example:443"), "hysteria2")
            validate_latest_subscriptions(destination)

    def test_master_aggregate_is_the_exact_union_and_base64_matches(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "latest"
            index = write_latest_subscriptions(destination, {
                _vless(1): 1,
                "trojan://pw@t.example:443": 10,
                "anytls://pw@a.example:443": 5,
            }, "2026-11-21T00:00:00Z")
            combined = (destination / "all.txt").read_bytes()
            self.assertEqual(
                base64.b64decode((destination / "all_base64.txt").read_bytes()),
                combined,
            )
            self.assertEqual(combined.decode().splitlines()[0], "trojan://pw@t.example:443")
            self.assertEqual(index["aggregate"]["count"], 3)
            self.assertEqual(
                {line for line in combined.decode().splitlines()},
                {line for name in index["protocols"]
                 for line in (destination / f"{name}.txt").read_text().splitlines()},
            )
            self.assertEqual(index["scope"], "all_time_cumulative")
            self.assertEqual(index["health_status"], "historical_unverified")
            self.assertEqual(
                json.loads((destination / "index.json").read_text()), index,
            )
            validate_latest_subscriptions(destination)

    def test_validator_detects_feed_tampering_and_missing_mirror_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "latest"
            write_latest_subscriptions(destination, {_vless(1): 100}, "2026-11-21T00:00:00Z")
            (destination / "all.txt").write_text(_vless(2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum|aggregate|digest|base64"):
                validate_latest_subscriptions(destination)

            write_latest_subscriptions(destination, {_vless(1): 100}, "2026-11-21T00:00:00Z")
            (destination / "vless_base64.txt").unlink()
            with self.assertRaises(ValueError):
                validate_latest_subscriptions(destination)

    def test_pages_validation_rejects_mirror_tampering(self):
        import hashlib
        import importlib.util
        import shutil

        spec = importlib.util.spec_from_file_location(
            "validate_pages_package",
            ROOT / "scripts" / "validate_pages_package.py",
        )
        assert spec is not None and spec.loader is not None
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "docs"
            root.mkdir()
            (root / "index.html").write_text("<html><body>HUNTX</body></html>")
            public = root / "subscriptions" / "latest"
            write_latest_subscriptions(public, {_vless(1): 1}, "2026-11-21T00:00:00Z")
            mirror = root / "artifacts" / "dev" / "latest"
            shutil.copytree(public, mirror)
            files = []
            for item in mirror.iterdir():
                contents = item.read_bytes()
                files.append({
                    "path": f"artifacts/dev/latest/{item.name}",
                    "size": len(contents),
                    "sha256": hashlib.sha256(contents).hexdigest(),
                })
            (root / "catalog.json").write_text(
                json.dumps({"files": files}), encoding="utf-8"
            )
            validator.validate_pages_package(root)

            (public / "vless.txt").write_bytes(b"modified\\n")
            with self.assertRaises(ValueError):
                validator.validate_pages_package(root)

            shutil.copy2(mirror / "vless.txt", public / "vless.txt")
            (mirror / "vless.txt").write_bytes(b"modified\\n")
            with self.assertRaises(ValueError):
                validator.validate_pages_package(root)

    def test_repeated_publish_is_byte_for_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifests = {
                _vless(1): 100,
                "trojan://pw@t.example:443": 1,
            }
            for dirname in ("one", "two"):
                write_latest_subscriptions(root / dirname, manifests, "2026-11-21T00:00:00Z")
            one = {p.name: p.read_bytes() for p in (root / "one").iterdir()}
            two = {p.name: p.read_bytes() for p in (root / "two").iterdir()}
            self.assertEqual(one, two)


if __name__ == "__main__":
    unittest.main()


class SlipNetAndAllFamiliesTests(unittest.TestCase):
    @staticmethod
    def _slipnet(index: int) -> str:
        # SlipNet's own exporter serializes a v30 pipe-delimited profile
        # and base64-encodes it after the slipnet:// prefix.
        fields = [
            "30", "dnstt", f"Public {index}", f"node{index}.example",
            "1.1.1.1:53:0", "0", "5000", "bbr", "443",
            f"node{index}.example", "0",
        ] + [""] * 73
        encoded = base64.b64encode("|".join(fields).encode("utf-8")).decode("ascii")
        return "slipnet://" + encoded

    def test_plain_slipnet_profiles_are_validated_and_ingested(self):
        from huntx.core.router import decide_format
        from huntx.formats.npvt import NpvtHandler
        from huntx.formats.proxy_uri_validator import validate_proxy_uri

        valid = self._slipnet(1)
        self.assertTrue(validate_proxy_uri(valid))
        self.assertEqual(protocol_for_uri(valid), "slipnet")
        self.assertEqual(decide_format("public-profiles.txt", valid.encode()), "npvt")
        records = NpvtHandler().parse(valid.encode(), {})
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["data"]["line"], valid)

        for invalid in (
            "slipnet://not-base64",
            "slipnet://"+base64.b64encode(b"abc").decode(),
            "slipnet://"+base64.b64encode(b"31|dnstt|profile|host.example").decode(),
            "slipnet-enc://"+valid.split("://", 1)[1],
            "slipnet-bundle-enc://"+valid.split("://", 1)[1],
        ):
            self.assertIsNone(protocol_for_uri(invalid))

    def test_requested_families_publish_independently_and_aggregate_exact_union(self):
        variants = [
            "trojan://pw@trojan.example:443",
            "socks4://socks.example:1080",
            "socks5://socks.example:1081",
            "hysteria://hysteria.example:443?auth=pw",
            "hysteria2://pw@hysteria2.example:443",
            "anytls://pw@anytls.example:443",
            "dns://dns.example:53",
            "dnstt://dnstt.example:53",
            "http://user:pw@proxy.example:8080",
            "https://user:pw@proxy.example:8443",
            self._slipnet(1),
        ]
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "latest"
            idx = write_latest_subscriptions(
                dest, {uri: n + 1 for n, uri in enumerate(variants)},
                "2026-11-22T00:00:00Z",
            )
            expected = {
                "trojan": 1, "socks": 2, "hysteria": 1,
                "hysteria2": 1, "anytls": 1, "dns": 1,
                "dnstt": 1, "http": 2, "slipnet": 1,
            }
            self.assertTrue(set(expected) <= set(PROTOCOL_CATEGORIES))
            for family, count in expected.items():
                self.assertEqual(idx["protocols"][family]["count"], count, family)
                plain = (dest / f"{family}.txt").read_bytes()
                decoded = base64.b64decode((dest / f"{family}_base64.txt").read_bytes())
                self.assertEqual(decoded, plain, family)
            aggregate = (dest / "all.txt").read_text().splitlines()
            self.assertEqual(len(aggregate), len(variants))
            self.assertEqual(set(aggregate), set(variants))
            validate_latest_subscriptions(dest)
