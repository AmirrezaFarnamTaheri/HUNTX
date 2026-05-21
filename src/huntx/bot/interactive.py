import asyncio
import datetime
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    from telethon import TelegramClient, events, Button
    from telethon.tl.functions.bots import SetBotCommandsRequest
    from telethon.tl.types import BotCommand, BotCommandScopeDefault
except ModuleNotFoundError:  # pragma: no cover
    TelegramClient = None  # type: ignore[assignment]
    events = None  # type: ignore[assignment]
    Button = None  # type: ignore[assignment]
    SetBotCommandsRequest = None  # type: ignore[assignment]
    BotCommand = None  # type: ignore[assignment]
    BotCommandScopeDefault = None  # type: ignore[assignment]

from ..store.artifact_store import ArtifactStore
from ..state.repo import StateRepo
from ..state.db import open_db
from ..store import paths

logger = logging.getLogger(__name__)

# ── Bot text ──────────────────────────────────────────────────────────

WELCOME_TEXT = (
    "🛰 **GatherX — Free Proxy Configs**\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Fresh proxy configs from **49+ sources**, updated every 2 hours.\n"
    "VMess · VLESS · Trojan · SS · Hysteria2 · TUIC · WireGuard and more.\n\n"
    "📥 **Get Proxies**\n"
    "  /get — Download proxies (your default format)\n"
    "  /get `b64sub` — Base64 subscription link\n"
    "  /latest — All recent proxy files\n"
    "  /formats — See all available formats\n"
    "  /protocols — Supported proxy protocols\n"
    "  /count — Proxy count per protocol\n\n"
    "⚙️ **Settings**\n"
    "  /setformat — Change your preferred format\n"
    "  /mute · /unmute — Toggle auto-delivery\n"
    "  /myinfo — Your preferences\n"
    "  /status · /ping — System status\n\n"
    "Proxies are delivered automatically. Use /mute to stop."
)

_BOT_COMMANDS = [
    # Telethon is optional at import-time (tests can run without it); these are populated only if available.
    *(
        [
            BotCommand(command="start", description="🚀 Start and get proxies"),
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
            BotCommand(command="help", description="❓ Help"),
        ]
        if BotCommand is not None
        else []
    ),
]

SUPPORTED_FORMATS = [
    "npvt", "npvtsub", "ovpn", "npv4", "conf_lines",
    "ehi", "hc", "hat", "sip", "nm", "dark",
    "tut", "sks", "tmt", "opaque_bundle",
]

# All valid format names a user can request (includes derived formats)
_ALL_VALID_FORMATS = SUPPORTED_FORMATS + ["b64sub", "decoded.json"]

# Formats to auto-deliver (the most useful ones)
_AUTO_DELIVER_FORMATS = ("npvt", "b64sub")

# Human-readable format descriptions
_FORMAT_LABELS: Dict[str, str] = {
    "npvt": "📋 V2Ray/Xray proxy list",
    "npvtsub": "📋 NapsternetV subscription",
    "b64sub": "🔗 Base64 subscription (v2rayN/v2rayNG)",
    "decoded.json": "📊 Structured JSON (all proxies decoded)",
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


# ── Bot class ─────────────────────────────────────────────────────────

class InteractiveBot:
    def __init__(self, token: str, api_id: int, api_hash: str):
        if TelegramClient is None:
            raise RuntimeError("Telethon is required to run the bot. Install dependencies (pip install -e .).")
        self.token = token
        self.api_id = api_id
        self.api_hash = api_hash

        self.artifact_store = ArtifactStore()
        self.db = open_db(paths.STATE_DB_PATH)
        self.repo = StateRepo(self.db)

        self._init_tables()

        session_path = paths.DATA_DIR / "bot.session"
        self.client = TelegramClient(str(session_path), self.api_id, self.api_hash)

    # ── DB setup ──────────────────────────────────────────────────────

    def _init_tables(self):
        with self.db.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_users (
                    user_id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    username TEXT,
                    registered_at REAL NOT NULL,
                    muted INTEGER DEFAULT 0,
                    last_delivered_at REAL DEFAULT 0,
                    default_format TEXT DEFAULT 'npvt'
                )
                """
            )

    def _register_user(self, user_id: str, chat_id: str, username: Optional[str] = None) -> bool:
        """Register a user. Returns True if newly registered, False if already existed."""
        with self.db.connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM bot_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE bot_users SET chat_id = ?, username = ? WHERE user_id = ?",
                    (chat_id, username, user_id),
                )
                return False
            conn.execute(
                "INSERT INTO bot_users (user_id, chat_id, username, registered_at) VALUES (?, ?, ?, ?)",
                (user_id, chat_id, username, time.time()),
            )
            return True

    def _get_active_users(self) -> list:
        """Get all non-muted users for auto-delivery."""
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT user_id, chat_id FROM bot_users WHERE muted = 0"
            ).fetchall()

    def _get_user_count(self) -> dict:
        """Get user stats."""
        with self.db.connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM bot_users").fetchone()["c"]
            active = conn.execute("SELECT COUNT(*) AS c FROM bot_users WHERE muted = 0").fetchone()["c"]
            return {"total": total, "active": active, "muted": total - active}

    def _get_user_pref(self, user_id: str) -> str:
        """Get user's preferred default format."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT default_format FROM bot_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return row["default_format"] if row and row["default_format"] else "npvt"

    def _set_user_pref(self, user_id: str, fmt: str):
        """Set user's preferred default format."""
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE bot_users SET default_format = ? WHERE user_id = ?",
                (fmt, user_id),
            )

    def _get_user_info(self, user_id: str) -> Optional[dict]:
        """Get full user row."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM bot_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    # ── Entry points ──────────────────────────────────────────────────

    async def deliver_updates(self):
        """Connect, auto-send latest outputs to all registered users, disconnect.
        Called automatically after every pipeline run."""
        try:
            await self.client.start(bot_token=self.token)
            users = self._get_active_users()
            if not users:
                logger.info("[GatherX] No registered users — skipping delivery.")
                return

            # Find latest output files
            output_dir = paths.OUTPUT_DIR
            files_to_send = self._collect_delivery_files(output_dir)
            if not files_to_send:
                logger.info("[GatherX] No output files to deliver.")
                return

            logger.info(
                f"[GatherX] Delivering {len(files_to_send)} file(s) "
                f"to {len(users)} user(s)..."
            )

            delivered = 0
            failed = 0
            now = time.time()

            for user in users:
                chat_id = int(user["chat_id"])
                try:
                    # Send a summary message first
                    await self.client.send_message(
                        chat_id,
                        "🛰 **GatherX Update**\n"
                        f"Fresh proxy configs — {len(files_to_send)} file(s):",
                        parse_mode="md",
                    )
                    for fpath, caption in files_to_send:
                        await self.client.send_file(chat_id, fpath, caption=caption, parse_mode="md")
                        await asyncio.sleep(0.3)

                    # Update last_delivered_at
                    with self.db.connect() as conn:
                        conn.execute(
                            "UPDATE bot_users SET last_delivered_at = ? WHERE user_id = ?",
                            (now, user["user_id"]),
                        )
                    delivered += 1
                except Exception as e:
                    logger.warning(f"[GatherX] Failed to deliver to {user['user_id']}: {e}")
                    failed += 1

            logger.info(f"[GatherX] Delivery complete: {delivered} ok, {failed} failed.")
        except Exception as e:
            logger.error(f"[GatherX] Delivery error: {e}")
        finally:
            try:
                await self.client.disconnect()
            except Exception as e:
                logger.debug(f"[GatherX] Failed to disconnect bot client: {e}")
            # Allow Telethon internal tasks to finish cancellation
            await asyncio.sleep(0.25)

    def _register_handlers(self):
        """Register all event handlers and the callback query handler."""
        if events is None:
            raise RuntimeError("Telethon is required to run the bot. Install dependencies (pip install -e .).")
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
        self.client.add_event_handler(self._on_admin, events.NewMessage(pattern=r"(?i)/admin"))
        self.client.add_event_handler(self._on_callback, events.CallbackQuery())

    async def start(self):
        """Start the bot in persistent interactive mode (long-polling).

        This is designed to run as a standalone process, e.g.:
            huntx bot
        It connects via Telethon, registers the command menu with Telegram,
        sets up event handlers, and blocks on run_until_disconnected().
        """
        await self.client.start(bot_token=self.token)

        # Register command menu with Telegram
        try:
            if SetBotCommandsRequest is not None and BotCommandScopeDefault is not None:
                await self.client(SetBotCommandsRequest(
                    scope=BotCommandScopeDefault(),
                    lang_code="",
                    commands=_BOT_COMMANDS,
                ))
            logger.info("[GatherX] Bot commands menu registered.")
        except Exception as e:
            logger.warning(f"[GatherX] Failed to register commands: {e}")

        self._register_handlers()

        stats = self._get_user_count()
        logger.info(
            f"[GatherX] Bot started (long-polling) — {stats['total']} users "
            f"({stats['active']} active, {stats['muted']} muted)"
        )

        try:
            await self.client.run_until_disconnected()
        except Exception as e:
            logger.error(f"[GatherX] Bot error: {e}")
        finally:
            await self.client.disconnect()

    # ── Helpers ────────────────────────────────────────────────────────

    def _build_setformat_keyboard(self, user_id: str):
        current = self._get_user_pref(user_id)
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

    def _is_admin(self, user_id: str, username: Optional[str] = None) -> bool:
        import os
        admins_str = os.environ.get("HUNTX_ADMINS", "")
        if not admins_str:
            return False
        admins = [a.strip().lower() for a in admins_str.split(",") if a.strip()]
        user_id_str = str(user_id).lower()
        username_str = str(username or "").lower().lstrip("@")
        return user_id_str in admins or username_str in admins

    @staticmethod
    def _filename_matches_format(name: str, fmt: str) -> bool:
        """Match both internal (route.fmt) and exported (route_fmt_suffix.ext) naming."""
        n = name.lower()
        f = fmt.lower()

        if f in ("npvt", "npvtsub"):
            return n.endswith(f".{f}") or n.endswith(f"_{f}.txt")

        if f in ("b64sub", "npvt.b64sub", "npvtsub.b64sub"):
            return ".b64sub" in n or n.endswith("_b64sub.txt")

        if f in ("decoded.json", "npvt.decoded.json", "npvtsub.decoded.json"):
            return ".decoded.json" in n or n.endswith("_decoded.json")

        return (
            n.endswith(f".{f}")
            or n.endswith(f"_{f}.txt")
            or n.endswith(f"_{f}.json")
            or n.endswith(f"_{f}.zip")
        )

    def _collect_delivery_files(self, output_dir: Path, formats=None) -> List[tuple]:
        """Collect output files to deliver. Returns list of (path, caption).
        If formats is given, only include files whose name ends with one of those suffixes.
        If formats is None, uses _AUTO_DELIVER_FORMATS."""
        allowed = formats or _AUTO_DELIVER_FORMATS
        results = []
        if not output_dir.exists():
            return results

        for f in sorted(output_dir.iterdir()):
            if not f.is_file() or f.stat().st_size == 0:
                continue
            name = f.name

            # Filter: file must match at least one requested format.
            if not any(self._filename_matches_format(name, fmt) for fmt in allowed):
                continue

            size_kb = f.stat().st_size / 1024

            # Determine a nice caption
            if name.endswith(".npvt"):
                caption = f"📋 `{name}` — proxy URI list ({size_kb:.0f} KB)"
            elif "b64sub" in name:
                caption = f"🔗 `{name}` — base64 subscription ({size_kb:.0f} KB)"
            elif "decoded.json" in name:
                caption = f"📊 `{name}` — decoded JSON ({size_kb:.0f} KB)"
            elif name.endswith((".ovpn", ".ehi", ".hc", ".hat", ".sip", ".nm", ".dark", ".npv4")):
                caption = f"📦 `{name}` — config archive ({size_kb:.0f} KB)"
            else:
                caption = f"`{name}` ({size_kb:.0f} KB)"

            results.append((f, caption))

        return results

    async def _send_latest_to_user(self, chat_id: int, fmt: Optional[str] = None, days: int = 4):
        """Send latest artifacts to a user, optionally filtered by format."""
        files = self.artifact_store.list_archive(days=days)
        if not files:
            await self.client.send_message(chat_id, f"No artifacts in the last {days} day(s).")
            return 0

        sent = 0
        for f in files:
            if fmt and not f.name.endswith(f".{fmt}"):
                continue
            size_kb = f.stat().st_size / 1024
            await self.client.send_file(
                chat_id, f,
                caption=f"`{f.name}` ({size_kb:.0f} KB)",
                parse_mode="md",
            )
            sent += 1
            await asyncio.sleep(0.3)

        if sent == 0 and fmt:
            await self.client.send_message(chat_id, f"No artifacts matching `{fmt}`.")
        return sent

    # ── Command handlers ──────────────────────────────────────────────

    async def _on_start(self, event):
        """Register user and send welcome with quick-action buttons."""
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
            current = self._get_user_pref(user_id)
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

    async def _send_format_to_user(self, chat_id: int, fmt: str):
        """Send files matching a format to a user. Used by both /get and button callbacks."""
        if fmt not in _ALL_VALID_FORMATS:
            await self.client.send_message(
                chat_id,
                f"Unknown format `{fmt}`.\nUse /formats to see available formats.",
                parse_mode="md",
            )
            return

        output_dir = paths.OUTPUT_DIR
        sent = 0
        if output_dir.exists():
            for f in sorted(output_dir.iterdir()):
                if not f.is_file() or f.stat().st_size == 0:
                    continue
                if self._filename_matches_format(f.name, fmt):
                    size_kb = f.stat().st_size / 1024
                    label = _FORMAT_LABELS.get(fmt, fmt)
                    await self.client.send_file(
                        chat_id, f,
                        caption=f"{label}\n`{f.name}` ({size_kb:.0f} KB)",
                        parse_mode="md",
                    )
                    sent += 1
                    await asyncio.sleep(0.3)

        if sent == 0:
            sent = await self._send_latest_to_user(chat_id, fmt=fmt, days=4)

        if sent == 0:
            await self.client.send_message(
                chat_id,
                f"No files found for `{fmt}`.\n"
                f"The pipeline may not have produced this format yet.\n"
                f"Use /formats to see all options.",
                parse_mode="md",
            )

    async def _on_latest(self, event):
        """Send all recent artifacts: /latest [days]"""
        self._register_user(str(event.sender_id), str(event.chat_id))

        args = event.text.split()[1:]
        days = int(args[0]) if args and args[0].isdigit() else 4
        days = min(days, 30)

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
            current = self._get_user_pref(user_id)
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

    async def _on_ping(self, event):
        """Simple health check."""
        start = time.time()
        msg = await event.respond("🏓 Pong!")
        latency = (time.time() - start) * 1000
        await msg.edit(f"🏓 **Pong!**\nLatency: `{latency:.0f}ms`", parse_mode="md")

    def _get_system_stats(self) -> dict:
        """Query DB for general pipeline stats."""
        with self.db.connect() as conn:
            sources = conn.execute("SELECT COUNT(*) AS c FROM source_state").fetchone()["c"]
            files = conn.execute("SELECT COUNT(*) AS c FROM seen_files").fetchone()["c"]
            records = conn.execute("SELECT COUNT(*) AS c FROM records WHERE is_active=1").fetchone()["c"]
            return {"sources": sources, "files": files, "records": records}

    def _get_protocol_counts(self) -> Dict[str, int]:
        """Query DB and parse JSON to get counts per protocol."""
        from ..formats.npvt import _PROXY_SCHEMES
        
        counts: Dict[str, int] = {}
        with self.db.connect() as conn:
            # First, count non-npvt record types
            rows = conn.execute(
                "SELECT record_type, COUNT(*) as c FROM records WHERE is_active=1 AND record_type != 'npvt' GROUP BY record_type"
            ).fetchall()
            for r in rows:
                counts[r["record_type"]] = r["c"]
            
            # Dynamically build CASE SQL statement using SQLite native JSON support
            case_clauses = []
            for scheme in _PROXY_SCHEMES:
                proto = scheme.replace("://", "")
                case_clauses.append(
                    f"WHEN json_valid(data_json) = 1 AND LOWER(json_extract(data_json, '$.line')) LIKE '{scheme.lower()}%' THEN '{proto}'"
                )
            
            case_sql = f"""
                SELECT 
                    CASE 
                        {" ".join(case_clauses)}
                        ELSE 'other'
                    END as sub_proto,
                    COUNT(*) as c
                FROM records 
                WHERE is_active=1 AND record_type = 'npvt'
                GROUP BY sub_proto
            """
            
            rows = conn.execute(case_sql).fetchall()
            for r in rows:
                sub_proto = r["sub_proto"]
                counts[sub_proto] = counts.get(sub_proto, 0) + r["c"]
                
        return counts


    # ── Inline button callback handler ─────────────────────────────

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
                    current = self._get_user_pref(user_id)
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
                if not self._is_admin(user_id, username):
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

    # ── Callback-friendly response methods ─────────────────────────

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
        await self.client.send_message(chat_id, "\n".join(lines), parse_mode="md", buttons=buttons)

    async def _respond_myinfo(self, chat_id: int, user_id: str, event=None):
        """Send or edit user settings to a chat."""
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
            await self.client.send_message(chat_id, msg, parse_mode="md", buttons=buttons)

    async def deliver_updates_active(self):
        """Send latest outputs to active users without connect/disconnect cycle."""
        users = self._get_active_users()
        if not users:
            logger.info("[GatherX] No registered users — skipping delivery.")
            return

        # Find latest output files
        output_dir = paths.OUTPUT_DIR
        files_to_send = self._collect_delivery_files(output_dir)
        if not files_to_send:
            logger.info("[GatherX] No output files to deliver.")
            return

        logger.info(
            f"[GatherX] Delivering {len(files_to_send)} file(s) "
            f"to {len(users)} user(s)..."
        )

        now = time.time()
        for user in users:
            chat_id = int(user["chat_id"])
            try:
                await self.client.send_message(
                    chat_id,
                    "🛰 **GatherX Update**\n"
                    f"Fresh proxy configs — {len(files_to_send)} file(s):",
                    parse_mode="md",
                )
                for fpath, caption in files_to_send:
                    await self.client.send_file(chat_id, fpath, caption=caption, parse_mode="md")
                    await asyncio.sleep(0.3)

                with self.db.connect() as conn:
                    conn.execute(
                        "UPDATE bot_users SET last_delivered_at = ? WHERE user_id = ?",
                        (now, user["user_id"]),
                    )
            except Exception as e:
                logger.warning(f"[GatherX] Failed to deliver to {user['user_id']}: {e}")

    async def _on_admin(self, event):
        """Secure admin control room command."""
        user_id = str(event.sender_id)
        
        sender = await event.get_sender()
        username = getattr(sender, "username", None)
        
        if not self._is_admin(user_id, username):
            await event.respond("❌ **Access Denied**\nThis command is restricted to administrators.", parse_mode="md")
            return
            
        args = event.text.split()[1:]
        if args:
            sub = args[0].lower()
            if sub == "run":
                await self._trigger_background_run(event)
                return
            elif sub == "prune":
                days = 30
                if len(args) > 1 and args[1].isdigit():
                    days = int(args[1])
                await self._perform_admin_prune(event, days)
                return
                
        # Show interactive dashboard
        await self._respond_admin_dashboard(event)

    async def _respond_admin_dashboard(self, event, edit=False):
        users = self._get_user_count()
        system = self._get_system_stats()
        
        msg = (
            "🛠 **GatherX Restricted Admin Panel**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 **Users:** `{users['total']}` (`{users['active']}` active, `{users['muted']}` muted)\n"
            f"📡 **Sources:** `{system['sources']}`\n"
            f"📄 **Seen Files:** `{system['files']}`\n"
            f"💎 **Active Records:** `{system['records']}`\n"
        )
        
        buttons = [
            [Button.inline("⚡ Trigger Pipeline Run", b"admin:run")],
            [Button.inline("🧹 Prune Database (30 Days)", b"admin:prune:30"),
             Button.inline("🧹 Prune Database (15 Days)", b"admin:prune:15")],
            [Button.inline("📊 Refresh Stats", b"admin:stats")]
        ]
        
        if edit:
            await event.edit(msg, parse_mode="md", buttons=buttons)
        else:
            await event.respond(msg, parse_mode="md", buttons=buttons)

    async def _trigger_background_run(self, event):
        """Trigger background pipeline run and notify upon completion."""
        if hasattr(event, "answer"):
            await event.answer("Starting pipeline run...")
            
        await event.respond("⚡ **Pipeline execution started in background...**\nAn update will be sent when complete.", parse_mode="md")
        
        loop = asyncio.get_running_loop()
        
        async def run_pipeline_task():
            try:
                await loop.run_in_executor(None, self._run_pipeline_blocking)
                await self.deliver_updates_active()
                await self.client.send_message(event.chat_id, "✅ **Pipeline execution and subscription delivery completed successfully!**", parse_mode="md")
            except Exception as ex:
                logger.exception(f"Background pipeline run failed: {ex}")
                await self.client.send_message(event.chat_id, f"❌ **Pipeline execution failed:**\n`{ex}`", parse_mode="md")
                
        asyncio.create_task(run_pipeline_task())

    def _run_pipeline_blocking(self):
        from ..core.orchestrator import Orchestrator
        from ..config.loader import load_config
        from ..config.validate import validate_config
        from ..core.locks import acquire_lock
        import os
        
        config_path = os.environ.get("HUNTX_CONFIG", "config.yaml")
        config = load_config(config_path)
        validate_config(config)
        
        lock_path = paths.STATE_DIR / "huntx.lock"
        with acquire_lock(lock_path):
            orchestrator = Orchestrator(config)
            no_publish = os.environ.get("HUNTX_BOT_NO_PUBLISH", "false").lower() == "true"
            orchestrator.run(timeout=16200, no_publish=no_publish)

    async def _perform_admin_prune(self, event, days):
        """Invoke repo and raw store pruning and report counts."""
        from ..store.raw_store import RawStore
        
        if hasattr(event, "answer"):
            await event.answer(f"Pruning database ({days} days)...")
            
        msg = await event.respond(f"🧹 **Pruning database and raw store (older than {days} days)...**", parse_mode="md")
        
        try:
            loop = asyncio.get_running_loop()
            
            def prune_blocking():
                raw_store = RawStore()
                res = self.repo.prune_old_data(days)
                raw_pruned = 0
                if res["raw_hashes"]:
                    raw_pruned = raw_store.prune_by_hashes(res["raw_hashes"])
                return res, raw_pruned
                
            res, raw_pruned = await loop.run_in_executor(None, prune_blocking)
            
            report = (
                f"✅ **Pruning Complete (Older than {days} days)**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📄 **Seen Files Pruned:** `{res.get('seen_files', 0)}`\n"
                f"💎 **Records Pruned:** `{res.get('records', 0)}`\n"
                f"📦 **Published Artifacts Pruned:** `{res.get('published_artifacts', 0)}`\n"
                f"🧹 **Raw Disk Blobs Deleted:** `{raw_pruned}`"
            )
            await msg.edit(report, parse_mode="md")
            
        except Exception as e:
            logger.exception(f"Admin pruning failed: {e}")
            await msg.edit(f"❌ **Pruning Failed:**\n`{e}`", parse_mode="md")





if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True)
    parser.add_argument("--api-id", type=int, required=True)
    parser.add_argument("--api-hash", required=True)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    bot = InteractiveBot(args.token, args.api_id, args.api_hash)
    asyncio.run(bot.start())
