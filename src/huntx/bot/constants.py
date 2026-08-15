try:
    from telethon.tl.types import BotCommand, BotCommandScopeDefault
except ModuleNotFoundError:
    BotCommand = None
    BotCommandScopeDefault = None

WELCOME_TEXT = (
    "🛰 **GatherX — Free Proxy Configs**\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Fresh proxy configs from **85 sources**, updated every 2 hours.\n"
    "VMess · VLESS · Trojan · SS · Hysteria2 · TUIC · WireGuard and more.\n\n"
    "📥 **Get Proxies**\n"
    "  /get — Download proxies (your default format)\n"
    "  /get `b64sub` — Base64 subscription link\n"
    "  /latest — All recent proxy files (max 7 days)\n"
    "  /formats — See all available formats\n"
    "  /protocols — Supported proxy protocols\n"
    "  /count — Proxy count per protocol\n\n"
    "⚙️ **Settings**\n"
    "  /setformat — Change your preferred format\n"
    "  /mute · /unmute — Toggle auto-delivery\n"
    "  /myinfo — Your preferences\n"
    "  /status · /ping — System status\n\n"
    "Proxies are delivered automatically. Use /mute to stop.\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ **Disclaimer:** All configurations are aggregated from public channels and are **unverified**. "
    "Use at your own risk; malicious proxy operators can observe/MITM your traffic."
)

_BOT_COMMANDS = [
    *(
        [
            BotCommand(command="start", description="🚀 Start and get proxies"),
            BotCommand(command="help", description="❓ Help"),
            BotCommand(command="get", description="📥 Download proxies"),
            BotCommand(command="latest", description="📦 Recent proxy files"),
            BotCommand(command="formats", description="📋 Available formats"),
            BotCommand(command="protocols", description="🔗 Supported protocols"),
            BotCommand(command="count", description="📊 Proxy count per protocol"),
            BotCommand(command="setformat", description="⚙️ Change default format"),
            BotCommand(command="myinfo", description="👤 Your preferences"),
            BotCommand(command="status", description="📈 Pipeline statistics"),
            BotCommand(command="mute", description="🔇 Stop auto-delivery"),
            BotCommand(command="unmute", description="🔔 Resume auto-delivery"),
            BotCommand(command="ping", description="🏓 Check bot status"),
        ]
        if BotCommand is not None
        else []
    ),
]

SUPPORTED_FORMATS = [
    "npvt",
    "npvtsub",
    "ovpn",
    "npv4",
    "conf_lines",
    "ehi",
    "hc",
    "hat",
    "sip",
    "nm",
    "dark",
    "tut",
    "sks",
    "tmt",
    "opaque_bundle",
]

_ALL_VALID_FORMATS = SUPPORTED_FORMATS + ["b64sub", "decoded.json", "singbox.json"]

_AUTO_DELIVER_FORMATS = ("npvt", "b64sub")

_FORMAT_LABELS = {
    "npvt": "📋 V2Ray/Xray proxy list",
    "npvtsub": "📋 NapsternetV subscription",
    "b64sub": "🔗 Base64 subscription (v2rayN/v2rayNG)",
    "decoded.json": "📊 Structured JSON (all proxies decoded)",
    "singbox.json": "📦 sing-box client config (import-ready)",
    "conf_lines": "📝 Generic config lines",
    "ovpn": "🔐 OpenVPN",
    "npv4": "📱 NapsternetV v4",
    "ehi": "📱 HTTP Injector",
    "hc": "📱 HTTP Custom",
    "hat": "📱 HA Tunnel Plus",
    "sip": "📱 SocksIP Tunnel",
    "nm": "📱 NetMod VPN",
    "dark": "📱 Dark Tunnel VPN",
    "tut": "📱 HCTools TUT Config",
    "sks": "📱 HCTools SKS Config",
    "tmt": "📱 HCTools TMT Config",
    "opaque_bundle": "📦 Binary bundle (ZIP)",
}
