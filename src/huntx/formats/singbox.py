"""Sing-box 1.10+ Multi-Outbound Config Compiler.

Authority:
    SagerNet Sing-box Specification: https://sing-box.sagernet.org/configuration/
    RFC 8446 (TLS 1.3): https://datatracker.ietf.org/doc/html/rfc8446
    RFC 7301 (ALPN): https://datatracker.ietf.org/doc/html/rfc7301
"""
from typing import Dict, Any, List, Optional

class SingboxCompiler:
    """Compiles normalized proxy records into Sing-box 1.10+ JSON schemas."""

    def __init__(
        self,
        listen_port: int = 7890,
        tun_enabled: bool = True,
        domestic_dns: str = "223.5.5.5",
        foreign_dns: str = "https://1.1.1.1/dns-query"
    ):
        self.listen_port = listen_port
        self.tun_enabled = tun_enabled
        self.domestic_dns = domestic_dns
        self.foreign_dns = foreign_dns

    def compile(self, nodes: List[Dict[str, Any]], default_route: Optional[str] = None) -> Dict[str, Any]:
        """Compile proxy records into a full Sing-box configuration dictionary."""
        outbounds: List[Dict[str, Any]] = []
        node_tags: List[str] = []
        reserved_tags = {"PROXY-AUTO", "AUTO-BEST", "direct", "block", "dns-out"}

        for node in nodes:
            proto = str(node.get("protocol", "")).lower()
            tag = node.get("tag") or f"{proto.upper()}-{node.get('server')}:{node.get('port')}"
            if tag in reserved_tags or tag in node_tags:
                continue
            if proto == "vless":
                outbound: Dict[str, Any] = {
                    "type": "vless",
                    "tag": tag,
                    "server": node.get("server"),
                    "server_port": int(node.get("port", 443)),
                    "uuid": node.get("uuid", ""),
                }
                if node.get("tls"):
                    outbound["tls"] = {
                        "enabled": True,
                        "server_name": node.get("sni") or node.get("server"),
                        "insecure": bool(node.get("allow_insecure", False)),
                    }
                if node.get("network") == "ws":
                    outbound["transport"] = {
                        "type": "ws",
                        "path": node.get("ws_path", "/"),
                        "headers": {"Host": node.get("host") or node.get("sni", "")}
                    }
                outbounds.append(outbound)
            elif proto == "hysteria2":
                outbound = {
                    "type": "hysteria2",
                    "tag": tag,
                    "server": node.get("server"),
                    "server_port": int(node.get("port", 443)),
                    "password": node.get("password", ""),
                    "tls": {
                        "enabled": True,
                        "server_name": node.get("sni") or node.get("server"),
                        "insecure": bool(node.get("allow_insecure", False)),
                    }
                }
                if node.get("obfs"):
                    outbound["obfs"] = {
                        "type": node.get("obfs"),
                        "password": node.get("obfs_password", "")
                    }
                outbounds.append(outbound)
            elif proto == "trojan":
                outbound = {
                    "type": proto,
                    "tag": tag,
                    "server": node.get("server"),
                    "server_port": int(node.get("port", 443)),
                    "password": node.get("password", ""),
                }
                if node.get("tls", True):
                    outbound["tls"] = {"enabled": True, "server_name": node.get("sni") or node.get("server"), "insecure": bool(node.get("allow_insecure", False))}
                if node.get("network") == "ws":
                    outbound["transport"] = {"type": "ws", "path": node.get("ws_path", "/"), "headers": {"Host": node.get("host") or node.get("sni", "")}}
                outbounds.append(outbound)
            elif proto == "vmess":
                outbound = {
                    "type": "vmess", "tag": tag, "server": node.get("server"),
                    "server_port": int(node.get("port", 443)), "uuid": node.get("uuid", ""),
                    "security": node.get("security", "auto"),
                }
                if node.get("tls"):
                    outbound["tls"] = {"enabled": True, "server_name": node.get("sni") or node.get("server"), "insecure": bool(node.get("allow_insecure", False))}
                if node.get("network") == "ws":
                    outbound["transport"] = {"type": "ws", "path": node.get("ws_path", "/"), "headers": {"Host": node.get("host") or node.get("sni", "")}}
                outbounds.append(outbound)
            elif proto == "shadowsocks":
                outbounds.append({
                    "type": "shadowsocks", "tag": tag, "server": node.get("server"),
                    "server_port": int(node.get("port", 8388)), "method": node.get("method") or node.get("cipher", ""),
                    "password": node.get("password", ""),
                })
            else:
                continue
            node_tags.append(tag)

        proxy_detour = "PROXY-AUTO" if node_tags else "direct"

        system_outbounds: List[Dict[str, Any]] = [
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
            {"type": "dns", "tag": "dns-out"},
        ]
        if node_tags:
            system_outbounds = [
            {
                "type": "selector",
                "tag": "PROXY-AUTO",
                "outbounds": ["AUTO-BEST"] + node_tags,
                "default": default_route if default_route in node_tags else (node_tags[0] if node_tags else "direct")
            },
            {
                "type": "urltest",
                "tag": "AUTO-BEST",
                "outbounds": node_tags,
                "url": "http://www.gstatic.com/generate_204",
                "interval": "3m",
                "tolerance": 50
            },
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
            {"type": "dns", "tag": "dns-out"},
        ]

        inbounds: List[Dict[str, Any]] = [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": self.listen_port,
                "sniff": True
            }
        ]
        if self.tun_enabled:
            inbounds.append({
                "type": "tun",
                "tag": "tun-in",
                "interface_name": "tun0",
                "inet4_address": "172.19.0.1/30",
                "auto_route": True,
                "strict_route": True,
                "stack": "system",
                "sniff": True
            })

        return {
            "log": {"level": "info", "timestamp": True},
            "dns": {
                "servers": [
                    {"tag": "remote-dns", "address": self.foreign_dns, "detour": proxy_detour},
                    {"tag": "local-dns", "address": self.domestic_dns, "detour": "direct"}
                ],
                "rules": [
                    {"geosite": "cn", "server": "local-dns"},
                    {"geosite": "category-ads-all", "server": "local-dns", "disable_cache": True}
                ]
            },
            "inbounds": inbounds,
            "outbounds": system_outbounds + outbounds,
            "route": {
                "rules": [
                    {"protocol": "dns", "outbound": "dns-out"},
                    {"geosite": "category-ads-all", "outbound": "block"},
                    {"geosite": "cn", "outbound": "direct"},
                    {"geoip": "cn", "outbound": "direct"},
                    {"geoip": "private", "outbound": "direct"}
                ],
                "auto_detect_interface": True
            }
        }
