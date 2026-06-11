import asyncio
import datetime
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
    "  /formats — See all available formats\n\n"
    "⚙️ **Settings**\n"
    "  /setformat — Change your preferred format\n"
    "  /mute · /unmute — Toggle auto-delivery\n"
    "  /myinfo — Your preferences\n\n"
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
            BotCommand(command="setformat", description="⚙️ Change default format"),
            BotCommand(command="myinfo", description="👤 Your preferences"),
            BotCommand(command="mute", description="🔇 Stop auto-delivery"),
            BotCommand(command="unmute", description="🔔 Resume auto-delivery"),
            BotCommand(command="help", description="❓ Help"),
        ]
        if BotCommand is not None
        else []
    ),
]

SUPPORTED_FORMATS = [
    "npvt", "npvtsub", "ovpn", "npv4", "conf_lines",
    "ehi", "hc", "hat", "sip", "nm", "dark", "opaque_bundle",
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
            output_dir = paths.DATA_DIR / "output"
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
        self.client.add_event_handler(self._on_mute, events.NewMessage(pattern=r"(?i)/mute"))
        self.client.add_event_handler(self._on_unmute, events.NewMessage(pattern=r"(?i)/unmute"))
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

        output_dir = DATA_DIR / "output"
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
            buttons = [
                [Button.inline("📋 npvt", b"setfmt:npvt"),
                 Button.inline("🔗 b64sub", b"setfmt:b64sub")],
                [Button.inline("📊 decoded.json", b"setfmt:decoded.json"),
                 Button.inline("🔐 ovpn", b"setfmt:ovpn")],
                [Button.inline("📱 ehi", b"setfmt:ehi"),
                 Button.inline("📱 hc", b"setfmt:hc"),
                 Button.inline("📱 hat", b"setfmt:hat")],
            ]
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

        info = self._get_user_info(user_id)
        if not info:
            await event.respond("Send /start to get started.")
            return

        last_del = "Not yet"
        if info["last_delivered_at"] and info["last_delivered_at"] > 0:
            last_del = datetime.datetime.fromtimestamp(info["last_delivered_at"]).strftime("%Y-%m-%d %H:%M UTC")

        muted_icon = "🔇" if info["muted"] else "🔔"
        muted_str = "Paused" if info["muted"] else "Active"
        fmt = info.get("default_format", "npvt")
        fmt_label = _FORMAT_LABELS.get(fmt, fmt)

        msg = (
            "⚙️ **Your Settings**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"  Download format: `{fmt}` ({fmt_label})\n"
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
        await event.respond(msg, parse_mode="md", buttons=buttons)

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
                    await event.answer(f"Default set to {fmt}")
                    await self.client.send_message(
                        chat_id,
                        f"✅ Default format set to `{fmt}` ({label})",
                        parse_mode="md",
                    )

            elif data.startswith("cmd:"):
                cmd = data.split(":", 1)[1]
                await event.answer()
                if cmd == "formats":
                    await self._respond_formats(chat_id)
                elif cmd == "myinfo":
                    await self._respond_myinfo(chat_id, user_id)
                elif cmd == "mute":
                    self._register_user(user_id, str(chat_id))
                    with self.db.connect() as conn:
                        conn.execute("UPDATE bot_users SET muted = 1 WHERE user_id = ?", (user_id,))
                    await self.client.send_message(chat_id, "🔇 Auto-delivery **paused**.", parse_mode="md")
                elif cmd == "unmute":
                    self._register_user(user_id, str(chat_id))
                    with self.db.connect() as conn:
                        conn.execute("UPDATE bot_users SET muted = 0 WHERE user_id = ?", (user_id,))
                    await self.client.send_message(chat_id, "🔔 Auto-delivery **resumed**.", parse_mode="md")
                elif cmd == "setformat":
                    current = self._get_user_pref(user_id)
                    label = _FORMAT_LABELS.get(current, current)
                    buttons = [
                        [Button.inline("📋 npvt", b"setfmt:npvt"),
                         Button.inline("🔗 b64sub", b"setfmt:b64sub")],
                        [Button.inline("📊 decoded.json", b"setfmt:decoded.json"),
                         Button.inline("🔐 ovpn", b"setfmt:ovpn")],
                    ]
                    await self.client.send_message(
                        chat_id,
                        f"⚙️ Current: `{current}` ({label})\nPick a new default:",
                        parse_mode="md",
                        buttons=buttons,
                    )
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

    async def _respond_myinfo(self, chat_id: int, user_id: str):
        """Send user settings to a chat (callback version)."""
        info = self._get_user_info(user_id)
        if not info:
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
        toggle_text = "🔇 Pause" if not info["muted"] else "🔔 Resume"
        toggle_data = b"cmd:mute" if not info["muted"] else b"cmd:unmute"
        buttons = [
            [Button.inline("⚙️ Change Format", b"cmd:setformat"),
             Button.inline(toggle_text, toggle_data)],
            [Button.inline("📥 Get Proxies", b"get:npvt")],
        ]
        await self.client.send_message(chat_id, msg, parse_mode="md", buttons=buttons)


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
