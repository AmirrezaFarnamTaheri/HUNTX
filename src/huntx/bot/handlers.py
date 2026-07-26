import logging
import time
import datetime
from typing import Dict, Any
from telethon import events, Button
from .constants import WELCOME_TEXT, _ALL_VALID_FORMATS, _FORMAT_LABELS

logger = logging.getLogger(__name__)


class HandlersMixin:
    # These methods are designed to be mixed into InteractiveBot.
    client: Any
    _user_cooldowns: Dict[Any, float]
    _get_user_pref: Any
    _is_admin: Any
    _get_user_info: Any

    def _register_handlers(self):
        """Register all event handlers and the callback query handler."""
        self.client.add_event_handler(self._on_start, events.NewMessage(pattern=r"(?i)/start"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_help, events.NewMessage(pattern=r"(?i)/help"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_get, events.NewMessage(pattern=r"(?i)/get"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_latest, events.NewMessage(pattern=r"(?i)/latest"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_formats, events.NewMessage(pattern=r"(?i)/formats"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_setformat, events.NewMessage(pattern=r"(?i)/setformat"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_myinfo, events.NewMessage(pattern=r"(?i)/myinfo"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_status, events.NewMessage(pattern=r"(?i)/status"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_protocols, events.NewMessage(pattern=r"(?i)/protocols"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_count, events.NewMessage(pattern=r"(?i)/count"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_ping, events.NewMessage(pattern=r"(?i)/ping"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_mute, events.NewMessage(pattern=r"(?i)/mute"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_unmute, events.NewMessage(pattern=r"(?i)/unmute"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_admin, events.NewMessage(pattern=r"(?i)/admin"))  # type: ignore[attr-defined]
        self.client.add_event_handler(self._on_callback, events.CallbackQuery())  # type: ignore[attr-defined]

    def _build_setformat_keyboard(self, user_id: str):
        current = self._get_user_pref(user_id)  # type: ignore[attr-defined]
        formats_layout = [
            [("npvt", "📋 npvt"), ("b64sub", "🔗 b64sub")],
            [("decoded.json", "📊 decoded"), ("ovpn", "🔐 ovpn")],
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

    async def _check_rate_limit(self, event, cooldown_seconds=5) -> bool:
        """Rate limit check to prevent resource exhaustion / flood-bans.
        Returns True if the request is allowed, False if it is rate-limited.
        """
        user_id = getattr(event, "sender_id", None)
        if not user_id:
            return True

        if self._is_admin(str(user_id)):  # type: ignore[attr-defined]
            return True

        now = time.time()
        last_time = self._user_cooldowns.get(user_id, 0.0)  # type: ignore[attr-defined]
        elapsed = now - last_time
        if elapsed < cooldown_seconds:
            wait_time = int(cooldown_seconds - elapsed) + 1
            await event.respond(f"⚠️ **Slow down!** Please wait {wait_time}s before using this command again.", parse_mode="md")
            return False

        self._user_cooldowns[user_id] = now  # type: ignore[attr-defined]
        return True

    async def _on_start(self, event):
        """Register user and send welcome with quick-action buttons."""
        if not await self._check_rate_limit(event, cooldown_seconds=3):
            return
        user_id = str(event.sender_id)
        chat_id = str(event.chat_id)
        username = None
        try:
            sender = await event.get_sender()
            username = getattr(sender, "username", None)
        except Exception as e:
            logger.debug(f"[GatherX] Failed to fetch sender info: {e}")

        is_new = self._register_user(user_id, chat_id, username)

        buttons = [
            [Button.inline("📥 Get Proxies", b"get:npvt"),
             Button.inline("🔗 Base64 Sub", b"get:b64sub")],
            [Button.inline("📋 All Formats", b"cmd:formats"),
             Button.inline("⚙️ Settings", b"cmd:myinfo")],
        ]
        await event.respond(WELCOME_TEXT, parse_mode="md", buttons=buttons)

        if is_new:
            logger.info(f"[GatherX] New user registered: {user_id} (@{username})")

    async def _on_help(self, event):
        if not await self._check_rate_limit(event, cooldown_seconds=3):
            return
        self._register_user(str(event.sender_id), str(event.chat_id))
        buttons = [
            [Button.inline("📥 Get Proxies", b"get:npvt"),
             Button.inline("🔗 Base64 Sub", b"get:b64sub")],
            [Button.inline("📋 All Formats", b"cmd:formats"),
             Button.inline("⚙️ Settings", b"cmd:myinfo")],
        ]
        await event.respond(WELCOME_TEXT, parse_mode="md", buttons=buttons)

    async def _on_get(self, event):
        """On-demand file download: /get [format]"""
        if not await self._check_rate_limit(event, cooldown_seconds=5):
            return
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))

        args = event.text.split()[1:]
        if not args:
            # No format specified → show quick-pick buttons
            buttons = [
                [Button.inline("📋 Proxy List (npvt)", b"get:npvt"),
                 Button.inline("🔗 Base64 Sub", b"get:b64sub")],
                [Button.inline("📊 Decoded JSON", b"get:decoded.json")],
                [Button.inline("🔐 OpenVPN", b"get:ovpn"),
                 Button.inline("📱 HTTP Injector", b"get:ehi")],
                [Button.inline("📱 HTTP Custom", b"get:hc"),
                 Button.inline("📱 HA Tunnel", b"get:hat")],
            ]
            current = self._get_user_pref(user_id)  # type: ignore[attr-defined]
            await event.respond(
                f"📥 **Download Configs**\n\n"
                f"Your default format: `{current}`\n"
                f"Pick a format below or type `/get <format>`:",
                parse_mode="md",
                buttons=buttons,
            )
            return

        fmt = args[0].lower()
        await self._send_format_to_user(event.chat_id, fmt)

    async def _on_latest(self, event):
        """Send all recent artifacts: /latest [days]"""
        if not await self._check_rate_limit(event, cooldown_seconds=15):
            return
        self._register_user(str(event.sender_id), str(event.chat_id))

        args = event.text.split()[1:]
        days = int(args[0]) if args and args[0].isdigit() else 4
        days = min(days, 7)

        await event.respond(f"📦 Fetching artifacts from the last {days} day(s)...")
        sent = await self._send_latest_to_user(event.chat_id, days=days)
        if sent == 0:
            await event.respond(
                f"No artifacts in the last {days} day(s).\n"
                f"Try a larger window: `/latest 7`",
                parse_mode="md",
            )
        else:
            await event.respond(f"✅ Sent {sent} file(s).")

    async def _on_formats(self, event):
        self._register_user(str(event.sender_id), str(event.chat_id))

        text_fmts = ["npvt", "npvtsub", "conf_lines", "b64sub", "decoded.json"]
        bin_fmts = ["ovpn", "npv4", "ehi", "hc", "hat", "sip", "nm", "dark"]

        lines = ["📋 **Available Formats**\n"]
        lines.append("**Text-based** (proxy URIs):")
        for f in text_fmts:
            label = _FORMAT_LABELS.get(f, f)
            lines.append(f"  `{f}` — {label}")
        lines.append("")
        lines.append("**Binary configs** (ZIP archives):")
        for f in bin_fmts:
            label = _FORMAT_LABELS.get(f, f)
            lines.append(f"  `{f}` — {label}")
        lines.append("\nUse `/get <format>` to download.")

        buttons = [
            [Button.inline("📋 Get npvt", b"get:npvt"),
             Button.inline("🔗 Get b64sub", b"get:b64sub")],
            [Button.inline("📊 Get decoded.json", b"get:decoded.json")],
        ]
        await event.respond("\n".join(lines), parse_mode="md", buttons=buttons)

    async def _on_setformat(self, event):
        """Set user's preferred default format: /setformat <fmt>"""
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))

        args = event.text.split()[1:]
        if not args:
            current = self._get_user_pref(user_id)  # type: ignore[attr-defined]
            label = _FORMAT_LABELS.get(current, current)
            buttons = self._build_setformat_keyboard(user_id)
            await event.respond(
                f"⚙️ **Set Default Format**\n\n"
                f"Current: `{current}` ({label})\n\n"
                f"Pick below or type `/setformat <format>`:",
                parse_mode="md",
                buttons=buttons,
            )
            return

        fmt = args[0].lower()
        if fmt not in _ALL_VALID_FORMATS:
            await event.respond(
                f"Unknown format `{fmt}`. Use /formats to see available options.",
                parse_mode="md",
            )
            return

        self._set_user_pref(user_id, fmt)
        label = _FORMAT_LABELS.get(fmt, fmt)
        await event.respond(
            f"✅ Default format set to `{fmt}` ({label})\n"
            f"`/get` will now download `{fmt}` files by default.",
            parse_mode="md",
        )

    async def _on_myinfo(self, event):
        """Show user's preferences and delivery settings."""
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))
        await self._respond_myinfo(event.chat_id, user_id)

    async def _on_mute(self, event):
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))
        with self.db.connect() as conn:
            conn.execute("UPDATE bot_users SET muted = 1 WHERE user_id = ?", (user_id,))
        await event.respond(
            "🔇 Auto-delivery **muted**.\n\n"
            "You won't receive automatic updates.\n"
            "Use /unmute to resume, or /get to download on demand.",
            parse_mode="md",
        )

    async def _on_unmute(self, event):
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))
        with self.db.connect() as conn:
            conn.execute("UPDATE bot_users SET muted = 0 WHERE user_id = ?", (user_id,))
        await event.respond(
            "🔔 Auto-delivery **resumed**.\n\n"
            "You'll receive updates after each pipeline run.",
            parse_mode="md",
        )

    async def _on_protocols(self, event):
        """Show supported proxy protocols."""
        from ..formats.npvt import _PROXY_SCHEMES
        schemes = sorted([s.replace("://", "") for s in _PROXY_SCHEMES])
        msg = (
            "🔗 **Supported Protocols**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "HuntX can detect, parse, and decode:\n\n"
            f"`{', '.join(schemes)}`"
        )
        await event.respond(msg, parse_mode="md")

    async def _on_count(self, event):
        """Show proxy counts per protocol with a simple bar chart."""
        await event.respond("📊 Calculating proxy counts...")
        counts = self._get_protocol_counts()
        if not counts:
            await event.respond("No proxies found in the database.")
            return

        total = sum(counts.values())
        lines = [f"📊 **Proxy Counts (Total: {total})**\n"]

        # Sort by count descending
        sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        max_count = sorted_counts[0][1] if sorted_counts else 1

        for proto, count in sorted_counts:
            pct = count / total * 100
            # Simple bar chart using unicode blocks
            bar_len = int((count / max_count) * 10)
            bar = "▇" * bar_len + "░" * (10 - bar_len)
            lines.append(f"`{proto:<10}` {bar} `{count:>4}` ({pct:>2.0f}%)")

        await event.respond("\n".join(lines), parse_mode="md")

    async def _on_ping(self, event):
        """Simple health check."""
        start = time.time()
        msg = await event.respond("🏓 Pong!")
        latency = (time.time() - start) * 1000
        await msg.edit(f"🏓 **Pong!**\nLatency: `{latency:.0f}ms`", parse_mode="md")

    async def _on_status(self, event):
        """Show system/pipeline statistics."""
        stats = self._get_system_stats()
        users = self._get_user_count()

        msg = (
            "📈 **System Status**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 **Users:** `{users['total']}` total (`{users['active']}` active)\n"
            f"📡 **Sources:** `{stats['sources']}` active Telegram channels\n"
            f"📄 **Files:** `{stats['files']}` processed blobs\n"
            f"💎 **Records:** `{stats['records']}` unique proxy configs\n"
        )
        await event.respond(msg, parse_mode="md")


    async def _on_callback(self, event):
        """Handle inline button presses."""
        data = event.data.decode("utf-8") if event.data else ""
        user_id = str(event.sender_id)
        chat_id = event.chat_id

        try:
            if data.startswith("get:"):
                fmt = data.split(":", 1)[1]
                await event.answer(f"Fetching {fmt}...")
                await self._send_format_to_user(chat_id, fmt)

            elif data.startswith("setfmt:"):
                fmt = data.split(":", 1)[1]
                if fmt in _ALL_VALID_FORMATS:
                    self._set_user_pref(user_id, fmt)
                    label = _FORMAT_LABELS.get(fmt, fmt)
                    await event.answer(f"Default set to {fmt} ✅")
                    buttons = self._build_setformat_keyboard(user_id)
                    await event.edit(
                        f"⚙️ **Set Default Format**\n\n"
                        f"Current: `{fmt}` ({label})\n\n"
                        f"Pick below or type `/setformat <format>`:",
                        parse_mode="md",
                        buttons=buttons,
                    )

            elif data.startswith("cmd:"):
                cmd = data.split(":", 1)[1]
                if cmd == "formats":
                    await event.answer()
                    await self._respond_formats(chat_id)
                elif cmd == "myinfo":
                    await event.answer()
                    await self._respond_myinfo(chat_id, user_id, event=event)
                elif cmd == "mute":
                    self._register_user(user_id, str(chat_id))
                    with self.db.connect() as conn:
                        conn.execute("UPDATE bot_users SET muted = 1 WHERE user_id = ?", (user_id,))
                    await event.answer("Auto-delivery paused 🔇")
                    await self._respond_myinfo(chat_id, user_id, event=event)
                elif cmd == "unmute":
                    self._register_user(user_id, str(chat_id))
                    with self.db.connect() as conn:
                        conn.execute("UPDATE bot_users SET muted = 0 WHERE user_id = ?", (user_id,))
                    await event.answer("Auto-delivery resumed 🔔")
                    await self._respond_myinfo(chat_id, user_id, event=event)
                elif cmd == "setformat":
                    await event.answer()
                    current = self._get_user_pref(user_id)  # type: ignore[attr-defined]
                    label = _FORMAT_LABELS.get(current, current)
                    buttons = self._build_setformat_keyboard(user_id)
                    await event.edit(
                        f"⚙️ **Set Default Format**\n\n"
                        f"Current: `{current}` ({label})\n\n"
                        f"Pick a new default format:",
                        parse_mode="md",
                        buttons=buttons,
                    )
            elif data.startswith("admin:"):
                sender = await event.get_sender()
                username = getattr(sender, "username", None)
                if not self._is_admin(user_id, username):  # type: ignore[attr-defined]
                    await event.answer("❌ Access Denied", alert=True)
                    return

                action = data.split(":", 1)[1]
                if action == "run":
                    await event.answer("Starting pipeline run...")
                    await self._trigger_background_run(event)
                elif action.startswith("prune:"):
                    days = int(action.split(":", 1)[1])
                    await self._perform_admin_prune(event, days)
                elif action == "stats":
                    await event.answer("Refreshing statistics...")
                    await self._respond_admin_dashboard(event, edit=True)
            else:
                await event.answer("Unknown action")
        except Exception as e:
            logger.exception(f"[GatherX] Callback error: {e}")
            await event.answer(f"Error: {e}"[:200])

    async def _respond_formats(self, chat_id: int):
        """Send formats list to a chat."""
        text_fmts = ["npvt", "npvtsub", "conf_lines", "b64sub", "decoded.json"]
        bin_fmts = ["ovpn", "npv4", "ehi", "hc", "hat", "sip", "nm", "dark"]
        lines = ["📋 **Available Formats**\n", "**Text-based:**"]
        for f in text_fmts:
            lines.append(f"  `{f}` — {_FORMAT_LABELS.get(f, f)}")
        lines.append("\n**Binary (ZIP):**")
        for f in bin_fmts:
            lines.append(f"  `{f}` — {_FORMAT_LABELS.get(f, f)}")
        lines.append("\nUse `/get <format>` to download.")
        buttons = [[Button.inline("📋 Get npvt", b"get:npvt"), Button.inline("🔗 Get b64sub", b"get:b64sub")]]
        await self.client.send_message(chat_id, "\n".join(lines), parse_mode="md", buttons=buttons)  # type: ignore[attr-defined]

    async def _respond_myinfo(self, chat_id: int, user_id: str, event=None):
        """Send or edit user settings to a chat."""
        info = self._get_user_info(user_id)  # type: ignore[attr-defined]
        if not info:
            if event:
                await event.respond("Send /start to get started.")
            else:
                await self.client.send_message(chat_id, "Send /start to get started.")  # type: ignore[attr-defined]
            return
        last_del = "Not yet"
        if info["last_delivered_at"] and info["last_delivered_at"] > 0:
            last_del = datetime.datetime.fromtimestamp(info["last_delivered_at"]).strftime("%Y-%m-%d %H:%M UTC")
        muted_icon = "🔇" if info["muted"] else "🔔"
        muted_str = "Paused" if info["muted"] else "Active"
        fmt = info.get("default_format", "npvt")
        msg = (
            f"⚙️ **Your Settings**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"  Download format: `{fmt}` ({_FORMAT_LABELS.get(fmt, fmt)})\n"
            f"  Auto-delivery: {muted_icon} {muted_str}\n"
            f"  Last received: {last_del}"
        )
        toggle_text = "🔇 Pause Delivery" if not info["muted"] else "🔔 Resume Delivery"
        toggle_data = b"cmd:mute" if not info["muted"] else b"cmd:unmute"
        buttons = [
            [Button.inline("⚙️ Change Format", b"cmd:setformat"),
             Button.inline(toggle_text, toggle_data)],
            [Button.inline("📥 Get Proxies", b"get:npvt")],
        ]
        if event:
            await event.edit(msg, parse_mode="md", buttons=buttons)
        else:
            await self.client.send_message(chat_id, msg, parse_mode="md", buttons=buttons)  # type: ignore[attr-defined]
