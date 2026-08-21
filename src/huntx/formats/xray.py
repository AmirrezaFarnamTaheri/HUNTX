"""Xray-core 1.8+ Multi-Outbound Config Compiler.

Authority:
    Project X / XTLS Specification: https://xtls.github.io/config/
    RFC 8446 (TLS 1.3): https://datatracker.ietf.org/doc/html/rfc8446
"""
from typing import Dict, Any, List

class XrayCompiler:
    """Compiles normalized proxy records into Xray-core 1.8+ JSON configuration."""

    def __init__(self, socks_port: int = 10808, http_port: int = 10809):
        self.socks_port = socks_port
        self.http_port = http_port

    def compile(self, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compile proxy records into an Xray configuration object."""
        outbounds: List[Dict[str, Any]] = []

        for node in nodes:
            proto = str(node.get("protocol", "")).lower()
            tag = node.get("tag") or f"{proto.upper()}-{node.get('server')}:{node.get('port')}"
            
            if proto == "vless":
                stream_settings: Dict[str, Any] = {"network": node.get("network", "tcp")}
                if node.get("pbk"): # Reality security
                    stream_settings["security"] = "reality"
                    stream_settings["realitySettings"] = {
                        "show": False,
                        "fingerprint": "chrome",
                        "serverName": node.get("sni") or node.get("server"),
                        "publicKey": node.get("pbk"),
                        "shortId": node.get("sid", ""),
                        "spiderX": ""
                    }
                elif node.get("tls"):
                    stream_settings["security"] = "tls"
                    stream_settings["tlsSettings"] = {
                        "allowInsecure": bool(node.get("allow_insecure", False)),
                        "serverName": node.get("sni") or node.get("server")
                    }

                outbounds.append({
                    "tag": tag,
                    "protocol": "vless",
                    "settings": {
                        "vnext": [{
                            "address": node.get("server"),
                            "port": int(node.get("port", 443)),
                            "users": [{
                                "id": node.get("uuid", ""),
                                "encryption": "none",
                                "flow": node.get("flow", "")
                            }]
                        }]
                    },
                    "streamSettings": stream_settings
                })
            elif proto == "vmess":
                stream_settings = {"network": node.get("network", "tcp")}
                if node.get("network") == "ws":
                    stream_settings["wsSettings"] = {
                        "path": node.get("ws_path", "/"),
                        "headers": {"Host": node.get("host") or node.get("sni", "")}
                    }
                if node.get("tls"):
                    stream_settings["security"] = "tls"
                    stream_settings["tlsSettings"] = {
                        "allowInsecure": bool(node.get("allow_insecure", False)),
                        "serverName": node.get("sni") or node.get("server")
                    }

                outbounds.append({
                    "tag": tag,
                    "protocol": "vmess",
                    "settings": {
                        "vnext": [{
                            "address": node.get("server"),
                            "port": int(node.get("port", 443)),
                            "users": [{
                                "id": node.get("uuid", ""),
                                "alterId": int(node.get("alter_id", 0)),
                                "security": "auto"
                            }]
                        }]
                    },
                    "streamSettings": stream_settings
                })

        outbounds.append({"tag": "direct", "protocol": "freedom", "settings": {}})
        outbounds.append({"tag": "block", "protocol": "blackhole", "settings": {}})

        return {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {
                    "tag": "socks-in",
                    "port": self.socks_port,
                    "listen": "127.0.0.1",
                    "protocol": "socks",
                    "settings": {"auth": "noauth", "udp": True},
                    "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}
                },
                {
                    "tag": "http-in",
                    "port": self.http_port,
                    "listen": "127.0.0.1",
                    "protocol": "http",
                    "settings": {"allowTransparent": False},
                    "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}
                }
            ],
            "outbounds": outbounds,
            "routing": {
                "domainStrategy": "IPIfNonMatch",
                "rules": [
                    {"type": "field", "outboundTag": "block", "domain": ["geosite:category-ads-all"]},
                    {"type": "field", "outboundTag": "direct", "domain": ["geosite:cn"]},
                    {"type": "field", "outboundTag": "direct", "ip": ["geoip:cn", "geoip:private"]}
                ]
            }
        }
