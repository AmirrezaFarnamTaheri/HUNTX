try:
    from telethon.tl.types import BotCommand, BotCommandScopeDefault
except ModuleNotFoundError:
    BotCommand = None
    BotCommandScopeDefault = None

# GatherX is deliberately a private-chat bot. These policy sets classify every
# non-admin command by the minimum authorization required after the DM check.
# Administrative commands are not advertised in Telegram's default menu.
_BOT_PUBLIC_COMMANDS = frozenset({"start", "help", "formats", "protocols", "myinfo", "ping"})
_BOT_APPROVED_COMMANDS = frozenset({"get", "latest", "count", "setformat", "mute", "unmute"})
_BOT_ADMIN_COMMANDS = frozenset({"status", "admin", "approve", "deny", "pending"})

WELCOME_TEXT = (
    "🛰 **GatherX — Free Proxy Configs**\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Fresh proxy configs from public sources, updated regularly.\n"
    "VMess · VLESS · Trojan · SS · Hysteria2 · TUIC · WireGuard and more.\n\n"
    "New registrations require administrator approval before proxy inventory, "
    "downloads, or delivery settings are available. GatherX works only in your DM.\n\n"
    "📥 **Approved access**\n"
    "  /get — Download proxies (your default format)\n"
    "  /get `b64sub` — Base64 subscription link\n"
    "  /latest — All recent proxy files (max 7 days)\n"
    "  /count — Proxy count per protocol\n\n"
    "ℹ️ **Available while pending**\n"
    "  /formats — See supported output formats\n"
    "  /protocols — Supported proxy protocols\n"
    "  /myinfo — Your registration/approval status\n"
    "  /ping — Check bot availability\n\n"
    "⚙️ **Approved settings**\n"
    "  /setformat — Change your preferred format\n"
    "  /mute · /unmute — Toggle auto-delivery\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ **Disclaimer:** All configurations are aggregated from public channels and are **unverified**. "
    "Use at your own risk; malicious proxy operators can observe/MITM your traffic."
)

_BOT_COMMANDS = [
    *(
        [
            BotCommand(command="start", description="🚀 Start / register"),
            BotCommand(command="help", description="❓ Help"),
            BotCommand(command="get", description="📥 Download proxies (approved)"),
            BotCommand(command="latest", description="📦 Recent proxy files (approved)"),
            BotCommand(command="formats", description="📋 Available formats"),
            BotCommand(command="protocols", description="🔗 Supported protocols"),
            BotCommand(command="count", description="📊 Proxy counts (approved)"),
            BotCommand(command="setformat", description="⚙️ Change default format (approved)"),
            BotCommand(command="myinfo", description="👤 Registration / preferences"),
            BotCommand(command="mute", description="🔇 Stop auto-delivery (approved)"),
            BotCommand(command="unmute", description="🔔 Resume auto-delivery (approved)"),
            BotCommand(command="ping", description="🏓 Check bot availability"),
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

_ALL_VALID_FORMATS = SUPPORTED_FORMATS + [
    "b64sub",
    "decoded.json",
    "raw.txt",
    "singbox.json",
    "xray.json",
    "nekobox.json",
]

_AUTO_DELIVER_FORMATS = ("npvt", "b64sub")

_FORMAT_LABELS = {
    "npvt": "📋 V2Ray/Xray proxy list",
    "npvtsub": "📋 NapsternetV subscription",
    "b64sub": "🔗 Base64 subscription (v2rayN/v2rayNG)",
    "decoded.json": "📊 Structured JSON (all proxies decoded)",
    "raw.txt": "📝 Raw proxy URI list",
    "singbox.json": "📦 sing-box client config (import-ready)",
    "xray.json": "📦 Xray client config (import-ready)",
    "nekobox.json": "📦 NekoBox sing-box outbound subscription",
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
