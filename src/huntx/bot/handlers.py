import datetime
import logging
import time
from typing import Any, Dict

from telethon import Button, events

from .constants import (
    WELCOME_TEXT,
    _ALL_VALID_FORMATS,
    _BOT_ADMIN_COMMANDS,
    _BOT_APPROVED_COMMANDS,
    _BOT_PUBLIC_COMMANDS,
    _FORMAT_LABELS,
)

logger = logging.getLogger(__name__)


class HandlersMixin:
    """Telegram command handlers mixed into :class:`InteractiveBot`."""

    client: Any
    _user_cooldowns: Dict[Any, float]
    _get_user_pref: Any
    _is_admin: Any
    _get_user_info: Any
    _require_private_chat: Any
    _require_approved: Any
    _require_admin: Any
    _on_callback: Any
    _on_admin: Any
    _on_approve: Any
    _on_deny: Any
    _on_pending: Any

    async def _require_named_access(self, event: Any, command: str) -> bool:
        """Apply the declared DM/approval/admin policy for one command."""
        if command in _BOT_PUBLIC_COMMANDS:
            return await self._require_private_chat(event)
        if command in _BOT_APPROVED_COMMANDS:
            return await self._require_approved(event)
        if command in _BOT_ADMIN_COMMANDS:
            if not await self._require_private_chat(event):
                return False
            return await self._require_admin(event)
        raise RuntimeError(f"Unclassified GatherX command: {command}")

    async def _policy_callback(self, event: Any) -> None:
        """Enforce callback authorization before dispatching the legacy callback body."""
        try:
            data = event.data.decode("utf-8", errors="strict") if event.data else ""
        except UnicodeDecodeError:
            await event.answer("Invalid action", alert=True)
            return

        if data.startswith("admin:"):
            allowed = await self._require_named_access(event, "admin")
        elif data.startswith(("get:", "setfmt:")):
            allowed = await self._require_named_access(event, "get")
        elif data in {"cmd:mute", "cmd:unmute", "cmd:setformat"}:
            allowed = await self._require_named_access(event, "setformat")
        elif data in {"cmd:formats", "cmd:myinfo"}:
            allowed = await self._require_named_access(event, "myinfo")
        else:
            allowed = await self._require_private_chat(event)
        if not allowed:
            return
        await self._on_callback(event)

    async def _private_admin(self, event: Any) -> None:
        if await self._require_named_access(event, "admin"):
            await self._on_admin(event)

    async def _private_approve(self, event: Any) -> None:
        if await self._require_named_access(event, "approve"):
            await self._on_approve(event)

    async def _private_deny(self, event: Any) -> None:
        if await self._require_named_access(event, "deny"):
            await self._on_deny(event)

    async def _private_pending(self, event: Any) -> None:
        if await self._require_named_access(event, "pending"):
            await self._on_pending(event)

    def _register_handlers(self):
        """Register command handlers through the declared authorization surface."""
        self.client.add_event_handler(self._on_start, events.NewMessage(pattern=r"(?i)/start"))
        self.client.add_event_handler(self._on_help, events.NewMessage(pattern=r"(?i)/help"))
        self.client.add_event_handler(self._on_get, events.NewMessage(pattern=r"(?i)/get"))
        self.client.add_event_handler(self._on_latest, events.NewMessage(pattern=r"(?i)/latest"))
        self.client.add_event_handler(self._on_formats, events.NewMessage(pattern=r"(?i)/formats"))
        self.client.add_event_handler(self._on_setformat, events.NewMessage(pattern=r"(?i)/setformat"))
        self.client.add_event_handler(self._on_myinfo, events.NewMessage(pattern=r"(?i)/myinfo"))
        self.client.add_event_handler(self._on_status, events.NewMessage(pattern=r"(?i)/status"))
        self.client.add_event_handler(self._on_protocols, events.NewMessage(pattern=r"(?i)/protocols"))
        self.client.add_event_handler(self._on_count, events.NewMessage(pattern=r"(?i)/count"))
        self.client.add_event_handler(self._on_ping, events.NewMessage(pattern=r"(?i)/ping"))
        self.client.add_event_handler(self._on_mute, events.NewMessage(pattern=r"(?i)/mute"))
        self.client.add_event_handler(self._on_unmute, events.NewMessage(pattern=r"(?i)/unmute"))
        self.client.add_event_handler(self._private_admin, events.NewMessage(pattern=r"(?i)/admin"))
        self.client.add_event_handler(
            self._private_approve,
            events.NewMessage(pattern=r"(?i)^/approve(?:\s|$)"),
        )
        self.client.add_event_handler(
            self._private_deny,
            events.NewMessage(pattern=r"(?i)^/deny(?:\s|$)"),
        )
        self.client.add_event_handler(
            self._private_pending,
            events.NewMessage(pattern=r"(?i)^/pending(?:\s|$)"),
        )
        self.client.add_event_handler(self._policy_callback, events.CallbackQuery())

    def _build_setformat_keyboard(self, user_id: str):
        """Build the inline keyboard for selecting a default delivery format."""
        current = self._get_user_pref(user_id)
        formats_layout = [
            [("npvt", "📋 npvt"), ("b64sub", "🔗 b64sub")],
            [("raw.txt", "📝 raw"), ("decoded.json", "📊 decoded")],
            [("singbox.json", "📦 sing-box"), ("xray.json", "📦 xray")],
            [("nekobox.json", "📦 nekobox"), ("ovpn", "🔐 ovpn")],
            [("ehi", "📱 ehi"), ("hc", "📱 hc")],
            [("hat", "📱 hat"), ("npv4", "📱 npv4")],
        ]
        buttons = []
        for row in formats_layout:
            row_buttons = []
            for fmt, label in row:
                display_label = f"✅ {label}" if current == fmt else label
                row_buttons.append(Button.inline(display_label, f"setfmt:{fmt}".encode("utf-8")))
            buttons.append(row_buttons)
        buttons.append([Button.inline("🔙 Back to Settings", b"cmd:myinfo")])
        return buttons

    async def _on_start(self, event):
        """Register a private-chat user and send the welcome panel."""
        if not await self._require_named_access(event, "start"):
            return
        if not await self._check_rate_limit(event, cooldown_seconds=3):
            return
        user_id = str(event.sender_id)
        chat_id = str(event.chat_id)
        username = None
        try:
            sender = await event.get_sender()
            username = getattr(sender, "username", None)
        except Exception as exc:
            logger.debug("[GatherX] Failed to fetch sender info: %s", exc)

        is_new = self._register_user(user_id, chat_id, username)
        buttons = [
            [Button.inline("📥 Get Proxies", b"get:npvt"), Button.inline("🔗 Base64 Sub", b"get:b64sub")],
            [Button.inline("📋 All Formats", b"cmd:formats"), Button.inline("⚙️ Settings", b"cmd:myinfo")],
        ]
        await event.respond(WELCOME_TEXT, parse_mode="md", buttons=buttons)
        if is_new:
            logger.info("[GatherX] New user registered: %s (@%s)", user_id, username)

    async def _on_help(self, event):
        """Send the private-chat help/welcome panel."""
        if not await self._require_named_access(event, "help"):
            return
        if not await self._check_rate_limit(event, cooldown_seconds=3):
            return
        self._register_user(str(event.sender_id), str(event.chat_id))
        buttons = [
            [Button.inline("📥 Get Proxies", b"get:npvt"), Button.inline("🔗 Base64 Sub", b"get:b64sub")],
            [Button.inline("📋 All Formats", b"cmd:formats"), Button.inline("⚙️ Settings", b"cmd:myinfo")],
        ]
        await event.respond(WELCOME_TEXT, parse_mode="md", buttons=buttons)

    async def _on_get(self, event):
        """Handle approved on-demand file download via ``/get [format]``."""
        if not await self._check_rate_limit(event, cooldown_seconds=5):
            return
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))
        if not await self._require_named_access(event, "get"):
            return

        args = event.text.split()[1:]
        if not args:
            buttons = [
                [Button.inline("📋 Proxy List (npvt)", b"get:npvt"), Button.inline("🔗 Base64 Sub", b"get:b64sub")],
                [Button.inline("📝 Raw Text", b"get:raw.txt"), Button.inline("📊 Decoded JSON", b"get:decoded.json")],
                [Button.inline("📦 sing-box JSON", b"get:singbox.json"), Button.inline("📦 Xray JSON", b"get:xray.json")],
                [Button.inline("📦 NekoBox JSON", b"get:nekobox.json")],
                [Button.inline("🔐 OpenVPN", b"get:ovpn"), Button.inline("📱 HTTP Injector", b"get:ehi")],
                [Button.inline("📱 HTTP Custom", b"get:hc"), Button.inline("📱 HA Tunnel", b"get:hat")],
            ]
            current = self._get_user_pref(user_id)
            await event.respond(
                f"📥 **Download Configs**\n\nYour default format: `{current}`\n"
                "Pick a format below or type `/get <format>`:",
                parse_mode="md",
                buttons=buttons,
            )
            return

        fmt = args[0].lower()
        await self._send_format_to_user(event.chat_id, fmt)

    async def _on_latest(self, event):
        """Send approved users all recent artifacts via ``/latest [days]``."""
        if not await self._check_rate_limit(event, cooldown_seconds=15):
            return
        self._register_user(str(event.sender_id), str(event.chat_id))
        if not await self._require_named_access(event, "latest"):
            return

        args = event.text.split()[1:]
        days = int(args[0]) if args and args[0].isdigit() else 4
        days = min(days, 7)
        await event.respond(f"📦 Fetching artifacts from the last {days} day(s)...")
        sent = await self._send_latest_to_user(event.chat_id, days=days)
        if sent == 0:
            await event.respond(
                f"No artifacts in the last {days} day(s).\nTry a larger window: `/latest 7`",
                parse_mode="md",
            )
        else:
            await event.respond(f"✅ Sent {sent} file(s).")

    async def _on_formats(self, event):
        """List format names in a private chat without exposing inventory."""
        if not await self._require_named_access(event, "formats"):
            return
        self._register_user(str(event.sender_id), str(event.chat_id))
        text_fmts = ["npvt", "npvtsub", "conf_lines", "b64sub", "raw.txt"]
        json_fmts = ["decoded.json", "singbox.json", "xray.json", "nekobox.json"]
        bin_fmts = ["ovpn", "npv4", "ehi", "hc", "hat", "sip", "nm", "dark"]
        lines = ["📋 **Available Formats**\n", "**Text-based** (proxy URIs):"]
        for fmt in text_fmts:
            lines.append(f"  `{fmt}` — {_FORMAT_LABELS.get(fmt, fmt)}")
        lines.append("")
        lines.append("**Client / structured JSON:**")
        for fmt in json_fmts:
            lines.append(f"  `{fmt}` — {_FORMAT_LABELS.get(fmt, fmt)}")
        lines.append("")
        lines.append("**Binary configs** (ZIP archives):")
        for fmt in bin_fmts:
            lines.append(f"  `{fmt}` — {_FORMAT_LABELS.get(fmt, fmt)}")
        lines.append("\nDownloads require approval. Use `/get <format>` after approval.")
        await event.respond("\n".join(lines), parse_mode="md")

    async def _on_setformat(self, event):
        """Set an approved user's preferred default format."""
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))
        if not await self._require_named_access(event, "setformat"):
            return
        args = event.text.split()[1:]
        if not args:
            current = self._get_user_pref(user_id)
            label = _FORMAT_LABELS.get(current, current)
            await event.respond(
                f"⚙️ **Set Default Format**\n\nCurrent: `{current}` ({label})\n\n"
                "Pick below or type `/setformat <format>`:",
                parse_mode="md",
                buttons=self._build_setformat_keyboard(user_id),
            )
            return
        fmt = args[0].lower()
        if fmt not in _ALL_VALID_FORMATS:
            await event.respond(f"Unknown format `{fmt}`. Use /formats to see available options.", parse_mode="md")
            return
        self._set_user_pref(user_id, fmt)
        label = _FORMAT_LABELS.get(fmt, fmt)
        await event.respond(
            f"✅ Default format set to `{fmt}` ({label})\n`/get` will now download `{fmt}` files by default.",
            parse_mode="md",
        )

    async def _on_myinfo(self, event):
        """Show the requesting private-chat user's registration state."""
        if not await self._require_named_access(event, "myinfo"):
            return
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))
        await self._respond_myinfo(event.chat_id, user_id)

    async def _on_mute(self, event):
        """Pause automatic delivery for an approved user."""
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))
        if not await self._require_named_access(event, "mute"):
            return
        with self.db.connect() as conn:
            conn.execute("UPDATE bot_users SET muted = 1 WHERE user_id = ?", (user_id,))
        await event.respond(
            "🔇 Auto-delivery **muted**.\n\nUse /unmute to resume, or /get to download on demand.",
            parse_mode="md",
        )

    async def _on_unmute(self, event):
        """Resume automatic delivery for an approved user."""
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))
        if not await self._require_named_access(event, "unmute"):
            return
        with self.db.connect() as conn:
            conn.execute("UPDATE bot_users SET muted = 0 WHERE user_id = ?", (user_id,))
        await event.respond("🔔 Auto-delivery **resumed**.", parse_mode="md")

    async def _on_protocols(self, event):
        """Show recognized proxy URI schemes without inventory counts."""
        if not await self._require_named_access(event, "protocols"):
            return
        from ..formats.npvt import _REPORT_PROXY_SCHEMES

        schemes = sorted({scheme.replace("://", "") for scheme in _REPORT_PROXY_SCHEMES})
        msg = (
            "🔗 **Supported Protocols**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "HuntX can detect, validate, and preserve:\n\n"
            f"`{', '.join(schemes)}`"
        )
        await event.respond(msg, parse_mode="md")

    async def _on_count(self, event):
        """Show proxy inventory counts only to approved private-chat users."""
        if not await self._require_named_access(event, "count"):
            return
        await event.respond("📊 Calculating proxy counts...")
        counts = self._get_protocol_counts()
        if not counts:
            await event.respond("No proxies found in the database.")
            return
        total = sum(counts.values())
        lines = [f"📊 **Proxy Counts (Total: {total})**\n"]
        sorted_counts = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        max_count = sorted_counts[0][1] if sorted_counts else 1
        for proto, count in sorted_counts:
            pct = count / total * 100
            bar_len = int((count / max_count) * 10)
            bar = "▇" * bar_len + "░" * (10 - bar_len)
            lines.append(f"`{proto:<10}` {bar} `{count:>4}` ({pct:>2.0f}%)")
        await event.respond("\n".join(lines), parse_mode="md")

    async def _on_ping(self, event):
        """Run a private-chat bot availability/latency check."""
        if not await self._require_named_access(event, "ping"):
            return
        start = time.time()
        msg = await event.respond("🏓 Pong!")
        latency = (time.time() - start) * 1000
        await msg.edit(f"🏓 **Pong!**\nLatency: `{latency:.0f}ms`", parse_mode="md")

    async def _on_status(self, event):
        """Show operational system statistics only to administrators."""
        if not await self._require_named_access(event, "status"):
            return
        stats = self._get_system_stats()
        users = self._get_user_count()
        msg = (
            "📈 **System Status**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 **Users:** `{users['total']}` total (`{users['active']}` active)\n"
            f"📡 **Sources:** `{stats['sources']}` active Telegram channels\n"
            f"📄 **Files:** `{stats['files']}` processed blobs\n"
            f"💎 **Records:** `{stats['records']}` unique proxy configs\n"
        )
        await event.respond(msg, parse_mode="md")

    async def _respond_formats(self, chat_id: int):
        """Send the public format-name list to an already private chat."""
        text_fmts = ["npvt", "npvtsub", "conf_lines", "b64sub", "raw.txt"]
        json_fmts = ["decoded.json", "singbox.json", "xray.json", "nekobox.json"]
        bin_fmts = ["ovpn", "npv4", "ehi", "hc", "hat", "sip", "nm", "dark"]
        lines = ["📋 **Available Formats**\n", "**Text-based:**"]
        for fmt in text_fmts:
            lines.append(f"  `{fmt}` — {_FORMAT_LABELS.get(fmt, fmt)}")
        lines.append("\n**Client / structured JSON:**")
        for fmt in json_fmts:
            lines.append(f"  `{fmt}` — {_FORMAT_LABELS.get(fmt, fmt)}")
        lines.append("\n**Binary (ZIP):**")
        for fmt in bin_fmts:
            lines.append(f"  `{fmt}` — {_FORMAT_LABELS.get(fmt, fmt)}")
        lines.append("\nDownloads require approval.")
        await self.client.send_message(chat_id, "\n".join(lines), parse_mode="md")

    async def _respond_myinfo(self, chat_id: int, user_id: str, event=None):
        """Send or edit a user's own settings/approval panel."""
        info = self._get_user_info(user_id)
        if not info:
            if event:
                await event.respond("Send /start to get started.")
            else:
                await self.client.send_message(chat_id, "Send /start to get started.")
            return
        last_del = "Not yet"
        if info["last_delivered_at"] and info["last_delivered_at"] > 0:
            last_del = datetime.datetime.fromtimestamp(info["last_delivered_at"]).strftime("%Y-%m-%d %H:%M UTC")
        muted_icon = "🔇" if info["muted"] else "🔔"
        muted_str = "Paused" if info["muted"] else "Active"
        fmt = info.get("default_format", "npvt")
        approved = bool(info.get("approved")) or self._is_admin(user_id)
        approval = "Approved" if approved else "Pending approval"
        msg = (
            "⚙️ **Your Settings**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"  Access: {approval}\n"
            f"  Download format: `{fmt}` ({_FORMAT_LABELS.get(fmt, fmt)})\n"
            f"  Auto-delivery: {muted_icon} {muted_str}\n"
            f"  Last received: {last_del}"
        )
        if approved:
            toggle_text = "🔇 Pause Delivery" if not info["muted"] else "🔔 Resume Delivery"
            toggle_data = b"cmd:mute" if not info["muted"] else b"cmd:unmute"
            buttons = [
                [Button.inline("⚙️ Change Format", b"cmd:setformat"), Button.inline(toggle_text, toggle_data)],
                [Button.inline("📥 Get Proxies", b"get:npvt")],
            ]
        else:
            buttons = [[Button.inline("📋 Available Formats", b"cmd:formats")]]
        if event:
            await event.edit(msg, parse_mode="md", buttons=buttons)
        else:
            await self.client.send_message(chat_id, msg, parse_mode="md", buttons=buttons)
