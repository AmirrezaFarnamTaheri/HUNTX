# Tests for Sing-box 1.10+ Multi-Outbound Config Compiler
# Authority: https://sing-box.sagernet.org/configuration/
from huntx.formats.singbox import SingboxCompiler

def test_singbox_compiler_initialization_defaults():
    compiler = SingboxCompiler()
    assert compiler.listen_port == 7890
    assert compiler.tun_enabled is True
    assert compiler.domestic_dns == "223.5.5.5"
    assert compiler.foreign_dns == "https://1.1.1.1/dns-query"

def test_singbox_compiler_compiles_vless_and_hysteria2_outbounds():
    compiler = SingboxCompiler(listen_port=7890, tun_enabled=True)
    sample_nodes = [
        {
            "protocol": "vless",
            "server": "1.1.1.1",
            "port": 443,
            "uuid": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
            "tag": "US-VLESS-01",
            "network": "ws",
            "tls": True,
            "sni": "speed.cloudflare.com",
            "ws_path": "/vless-ws",
        },
        {
            "protocol": "hysteria2",
            "server": "8.8.8.8",
            "port": 8443,
            "password": "secret_password",
            "tag": "DE-HY2-01",
            "sni": "hy2.example.com",
            "obfs": "salamander",
            "obfs_password": "obfs_secret",
        },
        {
            "protocol": "trojan",
            "server": "9.9.9.9",
            "port": 443,
            "password": "trojan_password",
            "tag": "SG-TROJAN-01",
            "sni": "sg.example.com"
        }
    ]
    config = compiler.compile(sample_nodes, default_route="US-VLESS-01")
    
    assert "inbounds" in config
    assert "outbounds" in config
    assert "route" in config
    assert "dns" in config
    
    # Check Inbounds
    inbound_types = [i["type"] for i in config["inbounds"]]
    assert "mixed" in inbound_types
    assert "tun" in inbound_types
    
    # Check System Outbounds
    outbound_tags = [o["tag"] for o in config["outbounds"]]
    assert "PROXY-AUTO" in outbound_tags
    assert "AUTO-BEST" in outbound_tags
    assert "direct" in outbound_tags
    assert "block" in outbound_tags
    assert "dns-out" in outbound_tags
    
    # Check Node Outbounds
    assert "US-VLESS-01" in outbound_tags
    assert "DE-HY2-01" in outbound_tags
    assert "SG-TROJAN-01" in outbound_tags
    
    vless_node = next(o for o in config["outbounds"] if o["tag"] == "US-VLESS-01")
    assert vless_node["type"] == "vless"
    assert vless_node["server"] == "1.1.1.1"
    assert vless_node["server_port"] == 443
    assert vless_node["uuid"] == "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
    assert vless_node["transport"]["type"] == "ws"
    assert vless_node["transport"]["path"] == "/vless-ws"
    assert vless_node["tls"]["server_name"] == "speed.cloudflare.com"
    
    hy2_node = next(o for o in config["outbounds"] if o["tag"] == "DE-HY2-01")
    assert hy2_node["type"] == "hysteria2"
    assert hy2_node["server"] == "8.8.8.8"
    assert hy2_node["password"] == "secret_password"
    assert hy2_node["obfs"]["type"] == "salamander"
    assert hy2_node["obfs"]["password"] == "obfs_secret"

def test_singbox_compiler_handles_empty_nodes():
    compiler = SingboxCompiler()
    config = compiler.compile([])
    assert len(config["outbounds"]) == 5 # PROXY-AUTO, AUTO-BEST, direct, block, dns-out
