# Tests for Xray-core 1.8+ Multi-Outbound Config Compiler
# Authority: https://xtls.github.io/config/
import pytest
from huntx.formats.xray import XrayCompiler

def test_xray_compiler_initialization():
    compiler = XrayCompiler(socks_port=10808, http_port=10809)
    assert compiler.socks_port == 10808
    assert compiler.http_port == 10809

def test_xray_compiler_generates_routing_and_outbounds():
    compiler = XrayCompiler(socks_port=10808, http_port=10809)
    sample_nodes = [
        {
            "protocol": "vless",
            "server": "104.16.1.1",
            "port": 443,
            "uuid": "11111111-2222-3333-4444-555555555555",
            "tag": "US-REALITY-01",
            "flow": "xtls-rprx-vision",
            "tls": True,
            "sni": "www.apple.com",
            "pbk": "abcdef1234567890",
            "sid": "12345678"
        },
        {
            "protocol": "vmess",
            "server": "1.0.0.1",
            "port": 443,
            "uuid": "22222222-3333-4444-5555-666666666666",
            "tag": "DE-VMESS-01",
            "network": "ws",
            "tls": True,
            "sni": "cloudflare.com",
            "ws_path": "/vmess-path"
        }
    ]
    config = compiler.compile(sample_nodes)
    assert "inbounds" in config
    assert "outbounds" in config
    assert "routing" in config
    
    # Check Inbounds
    inbound_tags = [i["tag"] for i in config["inbounds"]]
    assert "socks-in" in inbound_tags
    assert "http-in" in inbound_tags
    
    # Check Reality Outbound
    outbound = next(o for o in config["outbounds"] if o["tag"] == "US-REALITY-01")
    assert outbound["protocol"] == "vless"
    stream_settings = outbound["streamSettings"]
    assert stream_settings["security"] == "reality"
    assert stream_settings["realitySettings"]["publicKey"] == "abcdef1234567890"
    assert stream_settings["realitySettings"]["serverName"] == "www.apple.com"
    assert stream_settings["realitySettings"]["shortId"] == "12345678"
    
    # Check Routing Rules
    rules = config["routing"]["rules"]
    assert any("geosite:category-ads-all" in r.get("domain", []) for r in rules)
    assert any("geoip:cn" in r.get("ip", []) for r in rules)
