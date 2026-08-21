"""Smart Domain-Categorized DNS & Outbound Routing Rule Generator.

Authority:
    Sing-box Routing Rule Specification: https://sing-box.sagernet.org/configuration/route/rule/
    Clash Rule Specification: https://clash.wiki/configuration/rules.html
"""
from enum import Enum
from typing import List, Dict, Any

class RuleCategory(str, Enum):
    """Semantic domain categories for selective proxy routing."""
    STREAMING = "streaming"
    AI = "ai"
    DEVELOPER = "developer"
    DOMESTIC_DIRECT = "domestic_direct"
    AD_BLOCKING = "ad_blocking"

# Domain dictionaries by category
STREAMING_DOMAINS = [
    "netflix.com", "nflxvideo.net", "youtube.com", "googlevideo.com",
    "disneyplus.com", "hbo.com", "spotify.com", "twitch.tv"
]

AI_DOMAINS = [
    "openai.com", "chatgpt.com", "anthropic.com", "claude.ai",
    "gemini.google.com", "deepmind.google", "midjourney.com", "cohere.com"
]

DEV_DOMAINS = [
    "github.com", "githubusercontent.com", "gitlab.com", "docker.com",
    "npmjs.org", "pypi.org", "crates.io", "golang.org"
]

class SmartRuleGenerator:
    """Generates multi-protocol domain rulesets for client configurations."""

    def generate_singbox_rules(self) -> List[Dict[str, Any]]:
        """Generate Sing-box 1.10+ JSON route rules."""
        return [
            {"protocol": "dns", "outbound": "dns-out"},
            {"geosite": "category-ads-all", "outbound": "block"},
            {"domain_suffix": STREAMING_DOMAINS, "outbound": "PROXY-STREAMING"},
            {"domain_suffix": AI_DOMAINS, "outbound": "PROXY-AI"},
            {"domain_suffix": DEV_DOMAINS, "outbound": "PROXY-DEV"},
            {"geosite": "cn", "outbound": "direct"},
            {"geosite": "ir", "outbound": "direct"},
            {"geoip": "cn", "outbound": "direct"},
            {"geoip": "ir", "outbound": "direct"},
            {"geoip": "private", "outbound": "direct"},
        ]

    def generate_clash_rules(self) -> List[str]:
        """Generate Clash / Mihomo YAML rule lines."""
        rules: List[str] = [
            "RULE-SET,reject,REJECT",
        ]
        for d in STREAMING_DOMAINS:
            rules.append(f"DOMAIN-SUFFIX,{d},PROXY-STREAMING")
        for d in AI_DOMAINS:
            rules.append(f"DOMAIN-SUFFIX,{d},PROXY-AI")
        for d in DEV_DOMAINS:
            rules.append(f"DOMAIN-SUFFIX,{d},PROXY-DEV")
        rules.extend([
            "GEOIP,CN,DIRECT",
            "GEOIP,IR,DIRECT",
            "GEOIP,LAN,DIRECT",
            "MATCH,PROXY-AUTO"
        ])
        return rules
