# Full-Spectrum End-to-End Pipeline Lifecycle Integration Test Suite
# Authority: RFC 9000 (QUIC), FoxIO JA4+, NIST FIPS 180-4, Sing-box / Xray Core Specs
from huntx.pipeline.chain import DynamicChainSynthesizer, ChainStrategy
from huntx.pipeline.rule_gen import SmartRuleGenerator
from huntx.pipeline.sign import SupplyChainSigner
from huntx.formats.singbox import SingboxCompiler
from huntx.formats.xray import XrayCompiler


def test_full_spectrum_pipeline_lifecycle_e2e():
    # 1. Raw Node Ingestion & Provenance
    nodes = [
        {
            "id": "ir-relay-01",
            "protocol": "vless",
            "server": "185.10.10.1",
            "port": 443,
            "uuid": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
            "country": "IR",
            "ping": 25.0,
            "alive": True,
            "tag": "IR-Relay-01",
            "network": "ws",
            "tls": True,
            "sni": "speedtest.net",
            "ws_path": "/vless-ws"
        },
        {
            "id": "de-exit-01",
            "protocol": "hysteria2",
            "server": "95.216.1.1",
            "port": 8443,
            "auth": "secret-pass-de",
            "country": "DE",
            "ping": 65.0,
            "alive": True,
            "tag": "DE-Exit-01",
            "sni": "de.exit.net",
            "obfs": "salamander",
            "obfs_password": "pass"
        },
        {
            "id": "us-exit-01",
            "protocol": "trojan",
            "server": "104.20.0.1",
            "port": 443,
            "password": "pass3",
            "country": "US",
            "ping": 110.0,
            "alive": True,
            "tag": "US-Exit-01",
            "sni": "us.exit.net"
        },
    ]

    # 2. Multi-Hop Dynamic Chain Synthesis
    synth = DynamicChainSynthesizer(
        strategy=ChainStrategy.DOMESTIC_RELAY_INTERNATIONAL_EXIT,
        domestic_country="IR",
        max_composite_latency_ms=1200.0,
        max_chains=20
    )
    chains = synth.synthesize(nodes)
    assert len(chains) >= 1
    primary_chain = chains[0]
    assert primary_chain.relay_node["country"] == "IR"
    assert primary_chain.exit_node["country"] in ["DE", "US"]
    assert primary_chain.composite_latency_ms > 0

    # 3. Categorized Routing Rule Generation
    rule_gen = SmartRuleGenerator()
    singbox_rules = rule_gen.generate_singbox_rules()
    assert len(singbox_rules) >= 4
    assert any(r.get("outbound") == "PROXY-STREAMING" for r in singbox_rules)
    assert any(r.get("outbound") == "PROXY-AI" for r in singbox_rules)

    # 4. Multi-Core Client Format Compilation (Sing-box 1.10+ & Xray-core 1.8+)
    sb_compiler = SingboxCompiler()
    sb_config = sb_compiler.compile(nodes)
    assert "outbounds" in sb_config
    assert len(sb_config["outbounds"]) >= 3

    xray_compiler = XrayCompiler()
    xray_config = xray_compiler.compile(nodes)
    assert "outbounds" in xray_config
    assert len(xray_config["outbounds"]) >= 3

    # 5. Supply-Chain Cryptographic Signing & Tamper Verification
    signer = SupplyChainSigner(secret_key="prod-master-key-2026")
    payloads = {
        "singbox.json": sb_config,
        "xray.json": xray_config,
        "chains.json": [c.to_dict() for c in chains]
    }
    manifest = signer.generate_manifest(payloads)
    sig = signer.sign_manifest(manifest)

    # 6. Cryptographic Integrity Validation
    verification = signer.verify_manifest(manifest, sig)
    assert verification.is_valid is True
    assert verification.root_hash == manifest["root_hash"]
