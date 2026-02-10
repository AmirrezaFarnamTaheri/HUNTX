import asyncio
import datetime
import json as _json
import logging
import time
from pathlib import Path
from typing import List, Optional

from telethon import TelegramClient, events
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault

from ..store.artifact_store import ArtifactStore
from ..state.repo import StateRepo
from ..state.db import open_db
from ..store.paths import STATE_DB_PATH, DATA_DIR

logger = logging.getLogger(__name__)

# ── Bot text ──────────────────────────────────────────────────────────

WELCOME_TEXT = (
    "**Welcome to GatherX** 🛰\n\n"
    "I aggregate proxy configs from 49+ Telegram channels every 3 hours "
    "and deliver them straight to you.\n\n"
    "**You're now registered** — you'll automatically receive fresh proxy "
    "lists after every pipeline run.\n\n"
    "**Commands:**\n"
    "`/get [format]` — Download configs (default: your preferred format)\n"
    "`/latest [days]` — All recent artifacts (default: 4 days)\n"
    "`/formats` — List all supported formats\n"
    "`/protocols` — Supported proxy protocols\n"
    "`/count` — Proxy count per protocol\n"
    "`/setformat <fmt>` — Set your default format\n"
    "`/myinfo` — Your account & preferences\n"
    "`/status` — Pipeline statistics\n"
    "`/mute` / `/unmute` — Toggle auto-delivery\n"
    "`/ping` — Check if bot is alive\n"
    "`/help` — Show this message"
)

_BOT_COMMANDS = [
    BotCommand(command="start", description="Register and get started"),
    BotCommand(command="get", description="Download configs by format"),
    BotCommand(command="latest", description="Get all recent artifacts"),
    BotCommand(command="formats", description="List supported formats"),
    BotCommand(command="protocols", description="Supported proxy protocols"),
    BotCommand(command="count", description="Proxy count per protocol"),
    BotCommand(command="setformat", description="Set your default format"),
    BotCommand(command="myinfo", description="Your account & preferences"),
    BotCommand(command="status", description="Pipeline statistics"),
    BotCommand(command="mute", description="Stop auto-delivery"),
    BotCommand(command="unmute", description="Resume auto-delivery"),
    BotCommand(command="ping", description="Check if bot is alive"),
    BotCommand(command="help", description="Show help message"),
]

SUPPORTED_FORMATS = [
    "npvt", "npvtsub", "ovpn", "npv4", "conf_lines",
    "ehi", "hc", "hat", "sip", "nm", "dark", "opaque_bundle",
]

# Formats to auto-deliver (the most useful ones)
_AUTO_DELIVER_FORMATS = ("npvt", "npvt.b64sub")


# ── Bot class ─────────────────────────────────────────────────────────

class InteractiveBot:
    def __init__(self, token: str, api_id: int, api_hash: str):
        self.token = token
        self.api_id = api_id
        self.api_hash = api_hash

        self.artifact_store = ArtifactStore()
        self.db = open_db(STATE_DB_PATH)
        self.repo = StateRepo(self.db)

        self._init_tables()

        session_path = DATA_DIR / "bot.session"
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
            output_dir = DATA_DIR / "output"
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
            await self.client.disconnect()

    async def start(self):
        """Start the bot in persistent interactive mode (listens forever)."""
        await self.client.start(bot_token=self.token)

        # Register command menu
        try:
            await self.client(SetBotCommandsRequest(
                scope=BotCommandScopeDefault(),
                lang_code="",
                commands=_BOT_COMMANDS,
            ))
            logger.info("[GatherX] Bot commands menu registered.")
        except Exception as e:
            logger.warning(f"[GatherX] Failed to register commands: {e}")

        # Register handlers
        self.client.add_event_handler(self._on_start, events.NewMessage(pattern=r"(?i)/start"))
        self.client.add_event_handler(self._on_help, events.NewMessage(pattern=r"(?i)/help"))
        self.client.add_event_handler(self._on_get, events.NewMessage(pattern=r"(?i)/get"))
        self.client.add_event_handler(self._on_latest, events.NewMessage(pattern=r"(?i)/latest"))
        self.client.add_event_handler(self._on_formats, events.NewMessage(pattern=r"(?i)/formats"))
        self.client.add_event_handler(self._on_protocols, events.NewMessage(pattern=r"(?i)/protocols"))
        self.client.add_event_handler(self._on_count, events.NewMessage(pattern=r"(?i)/count"))
        self.client.add_event_handler(self._on_setformat, events.NewMessage(pattern=r"(?i)/setformat"))
        self.client.add_event_handler(self._on_myinfo, events.NewMessage(pattern=r"(?i)/myinfo"))
        self.client.add_event_handler(self._on_status, events.NewMessage(pattern=r"(?i)/status"))
        self.client.add_event_handler(self._on_mute, events.NewMessage(pattern=r"(?i)/mute"))
        self.client.add_event_handler(self._on_unmute, events.NewMessage(pattern=r"(?i)/unmute"))
        self.client.add_event_handler(self._on_ping, events.NewMessage(pattern=r"(?i)/ping"))

        stats = self._get_user_count()
        logger.info(
            f"[GatherX] Bot started — {stats['total']} users "
            f"({stats['active']} active, {stats['muted']} muted)"
        )

        try:
            await self.client.run_until_disconnected()
        except Exception as e:
            logger.error(f"[GatherX] Bot error: {e}")
        finally:
            await self.client.disconnect()

    # ── Helpers ────────────────────────────────────────────────────────

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

            # Filter: file must end with .{fmt} for at least one allowed format
            if not any(name.endswith(f".{fmt}") for fmt in allowed):
                continue

            size_kb = f.stat().st_size / 1024

            # Determine a nice caption
            if name.endswith(".npvt"):
                caption = f"📋 `{name}` — proxy URI list ({size_kb:.0f} KB)"
            elif "b64sub" in name:
                caption = f"� `{name}` — base64 subscription ({size_kb:.0f} KB)"
            elif "decoded.json" in name:
                caption = f"� `{name}` — decoded JSON ({size_kb:.0f} KB)"
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
        """Register user and send welcome + latest proxy list."""
        user_id = str(event.sender_id)
        chat_id = str(event.chat_id)
        username = None
        try:
            sender = await event.get_sender()
            username = getattr(sender, "username", None)
        except Exception:
            pass

        is_new = self._register_user(user_id, chat_id, username)
        await event.respond(WELCOME_TEXT, parse_mode="md")

        if is_new:
            logger.info(f"[GatherX] New user registered: {user_id} (@{username})")

        # Auto-send latest npvt + b64sub on /start
        await event.respond("Fetching your latest proxy configs...")
        sent = await self._send_latest_to_user(event.chat_id, fmt="npvt", days=2)
        sent += await self._send_latest_to_user(event.chat_id, fmt="npvt.b64sub", days=2)
        if sent == 0:
            await event.respond(
                "No proxy configs available yet. "
                "You'll receive them automatically after the next pipeline run."
            )

    async def _on_help(self, event):
        await event.respond(WELCOME_TEXT, parse_mode="md")

    async def _on_get(self, event):
        """On-demand file download: /get [format]"""
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))

        args = event.text.split()[1:]
        fmt = args[0].lower() if args else self._get_user_pref(user_id)

        if fmt not in SUPPORTED_FORMATS and fmt not in ("b64sub", "decoded.json"):
            await event.respond(
                f"Unknown format `{fmt}`.\n"
                f"Use `/formats` to see available formats.",
                parse_mode="md",
            )
            return

        # Search output dir for matching files
        output_dir = DATA_DIR / "output"
        sent = 0
        if output_dir.exists():
            for f in sorted(output_dir.iterdir()):
                if not f.is_file() or f.stat().st_size == 0:
                    continue
                if fmt in f.name:
                    size_kb = f.stat().st_size / 1024
                    await self.client.send_file(
                        event.chat_id, f,
                        caption=f"`{f.name}` ({size_kb:.0f} KB)",
                        parse_mode="md",
                    )
                    sent += 1
                    await asyncio.sleep(0.3)

        if sent == 0:
            # Fallback to archive
            sent = await self._send_latest_to_user(event.chat_id, fmt=fmt, days=4)

        if sent == 0:
            await event.respond(f"No files found for `{fmt}`. Try `/formats` to see what's available.", parse_mode="md")

    async def _on_latest(self, event):
        """Send all recent artifacts: /latest [days]"""
        self._register_user(str(event.sender_id), str(event.chat_id))

        args = event.text.split()[1:]
        days = int(args[0]) if args and args[0].isdigit() else 4

        sent = await self._send_latest_to_user(event.chat_id, days=days)
        if sent == 0:
            await event.respond(f"No artifacts in the last {days} day(s).")
        else:
            await event.respond(f"Sent {sent} file(s).")

    async def _on_formats(self, event):
        self._register_user(str(event.sender_id), str(event.chat_id))

        lines = [
            "**Available Formats:**\n",
            "**Text-based** (proxy URIs):",
            "  `npvt` — V2Ray/Xray proxy list (most popular)",
            "  `npvtsub` — NapsternetV subscription",
            "  `conf_lines` — Generic config lines",
            "  `b64sub` — Base64 subscription (v2rayN/v2rayNG)",
            "  `decoded.json` — Structured JSON of all proxies\n",
            "**Binary configs** (ZIP archives):",
            "  `ovpn` — OpenVPN",
            "  `npv4` — NapsternetV v4",
            "  `ehi` — HTTP Injector",
            "  `hc` — HTTP Custom",
            "  `hat` — HA Tunnel Plus",
            "  `sip` — SocksIP Tunnel",
            "  `nm` — NetMod VPN",
            "  `dark` — Dark Tunnel VPN\n",
            "Use `/get <format>` to download any of these.",
        ]
        await event.respond("\n".join(lines), parse_mode="md")

    async def _on_status(self, event):
        self._register_user(str(event.sender_id), str(event.chat_id))

        try:
            with self.db.connect() as conn:
                total_files = conn.execute("SELECT COUNT(*) AS c FROM seen_files").fetchone()["c"]
                processed = conn.execute(
                    "SELECT COUNT(*) AS c FROM seen_files WHERE status='processed'"
                ).fetchone()["c"]
                sources = conn.execute("SELECT COUNT(*) AS c FROM source_state").fetchone()["c"]
                records = conn.execute("SELECT COUNT(*) AS c FROM records WHERE is_active=1").fetchone()["c"]

            user_stats = self._get_user_count()

            msg = (
                "**GatherX Pipeline Status**\n\n"
                f"📡 Sources: {sources}\n"
                f"📁 Files processed: {processed}/{total_files}\n"
                f"📋 Active records: {records}\n"
                f"👥 Users: {user_stats['active']} active, {user_stats['muted']} muted"
            )
            await event.respond(msg, parse_mode="md")
        except Exception as e:
            await event.respond(f"Error: {e}")

    async def _on_protocols(self, event):
        """Show supported proxy protocols."""
        self._register_user(str(event.sender_id), str(event.chat_id))
        msg = (
            "**Supported Proxy Protocols**\n\n"
            "| Scheme | Protocol |\n"
            "|---|---|\n"
            "| `vmess://` | VMess (V2Ray) |\n"
            "| `vless://` | VLESS (Xray) |\n"
            "| `trojan://` | Trojan |\n"
            "| `ss://` | Shadowsocks |\n"
            "| `ssr://` | ShadowsocksR |\n"
            "| `hysteria2://` `hy2://` | Hysteria 2 |\n"
            "| `hysteria://` | Hysteria 1 |\n"
            "| `tuic://` | TUIC (QUIC) |\n"
            "| `wireguard://` `wg://` | WireGuard |\n"
            "| `socks://` `socks5://` | SOCKS proxy |\n"
            "| `anytls://` | AnyTLS |\n"
            "| `juicity://` | Juicity |\n"
            "| `warp://` | Cloudflare WARP |\n"
            "| `dns://` `dnstt://` | DNS tunnel |"
        )
        await event.respond(msg, parse_mode="md")

    async def _on_count(self, event):
        """Show proxy URI count per protocol from active records."""
        self._register_user(str(event.sender_id), str(event.chat_id))
        try:
            with self.db.connect() as conn:
                rows = conn.execute(
                    "SELECT data_json FROM records WHERE is_active = 1"
                ).fetchall()

            if not rows:
                await event.respond("No active records yet.")
                return

            counts = {}
            total = 0
            for row in rows:
                try:
                    data = _json.loads(row["data_json"])
                    lines = data.get("lines", []) if isinstance(data, dict) else []
                    for line in lines:
                        if "://" in line:
                            scheme = line.split("://")[0].lower()
                            counts[scheme] = counts.get(scheme, 0) + 1
                            total += 1
                except Exception:
                    pass

            if not counts:
                await event.respond("No proxy URIs found in active records.")
                return

            sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
            lines = [f"**Proxy URI Count** ({total} total)\n"]
            for scheme, cnt in sorted_counts:
                pct = cnt / total * 100
                bar = "█" * max(1, int(pct / 5))
                lines.append(f"`{scheme}` — {cnt} ({pct:.0f}%) {bar}")

            await event.respond("\n".join(lines), parse_mode="md")
        except Exception as e:
            await event.respond(f"Error: {e}")

    async def _on_setformat(self, event):
        """Set user's preferred default format: /setformat <fmt>"""
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))

        args = event.text.split()[1:]
        if not args:
            current = self._get_user_pref(user_id)
            await event.respond(
                f"Your current default format: `{current}`\n\n"
                f"Usage: `/setformat <format>`\n"
                f"Example: `/setformat ovpn`\n\n"
                f"Use `/formats` to see all options.",
                parse_mode="md",
            )
            return

        fmt = args[0].lower()
        all_valid = SUPPORTED_FORMATS + ["b64sub", "decoded.json"]
        if fmt not in all_valid:
            await event.respond(
                f"Unknown format `{fmt}`. Use `/formats` to see available options.",
                parse_mode="md",
            )
            return

        self._set_user_pref(user_id, fmt)
        await event.respond(
            f"Default format set to `{fmt}`.\n"
            f"`/get` will now download `{fmt}` files by default.",
            parse_mode="md",
        )

    async def _on_myinfo(self, event):
        """Show user's account info and preferences."""
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))

        info = self._get_user_info(user_id)
        if not info:
            await event.respond("No account info found. Send /start to register.")
            return

        reg_time = datetime.datetime.fromtimestamp(info["registered_at"]).strftime("%Y-%m-%d %H:%M")
        last_del = "Never"
        if info["last_delivered_at"] and info["last_delivered_at"] > 0:
            last_del = datetime.datetime.fromtimestamp(info["last_delivered_at"]).strftime("%Y-%m-%d %H:%M")

        muted_str = "🔇 Muted" if info["muted"] else "🔔 Active"
        username_str = f"@{info['username']}" if info.get("username") else "—"

        msg = (
            "**Your GatherX Account**\n\n"
            f"👤 Username: {username_str}\n"
            f"🆔 User ID: `{user_id}`\n"
            f"📅 Registered: {reg_time}\n"
            f"📦 Default format: `{info.get('default_format', 'npvt')}`\n"
            f"📬 Auto-delivery: {muted_str}\n"
            f"🕐 Last delivery: {last_del}"
        )
        await event.respond(msg, parse_mode="md")

    async def _on_ping(self, event):
        """Health check."""
        uptime_info = ""
        try:
            with self.db.connect() as conn:
                records = conn.execute("SELECT COUNT(*) AS c FROM records WHERE is_active=1").fetchone()["c"]
            uptime_info = f"\n📋 Active records: {records}"
        except Exception:
            pass
        await event.respond(f"🏓 **Pong!** GatherX is online.{uptime_info}", parse_mode="md")

    async def _on_mute(self, event):
        user_id = str(event.sender_id)
        with self.db.connect() as conn:
            conn.execute("UPDATE bot_users SET muted = 1 WHERE user_id = ?", (user_id,))
        await event.respond(
            "🔇 Auto-delivery **muted**. You won't receive automatic updates.\n"
            "Use `/unmute` to resume, or `/get` to download on demand.",
            parse_mode="md",
        )

    async def _on_unmute(self, event):
        user_id = str(event.sender_id)
        self._register_user(user_id, str(event.chat_id))
        with self.db.connect() as conn:
            conn.execute("UPDATE bot_users SET muted = 0 WHERE user_id = ?", (user_id,))
        await event.respond(
            "🔔 Auto-delivery **resumed**. You'll receive updates after each pipeline run.",
            parse_mode="md",
        )


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
