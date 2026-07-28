import asyncio
import logging
import os
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

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

from .constants import (
    _BOT_COMMANDS,
    _ALL_VALID_FORMATS,
    _FORMAT_LABELS,
)

# Re-exported as part of this module's public surface (consumed by the test
# suite and downstream importers); imported here rather than referenced.
from .constants import WELCOME_TEXT as WELCOME_TEXT  # noqa: F401
from .constants import SUPPORTED_FORMATS as SUPPORTED_FORMATS  # noqa: F401

from .handlers import HandlersMixin
from .delivery import DeliveryMixin
from .admin import AdminMixin

logger = logging.getLogger(__name__)


class InteractiveBot(HandlersMixin, DeliveryMixin, AdminMixin):
    _COOLDOWN_MAX_ENTRIES = 4096
    _COOLDOWN_TTL_SECONDS = 3600.0

    def __init__(self, token: str, api_id: int, api_hash: str):
        if TelegramClient is None:
            raise RuntimeError("Telethon is required to run the bot. Install dependencies (pip install -e .).")

        ingest_token = os.environ.get("TELEGRAM_TOKEN")
        allow_shared = os.environ.get("HUNTX_ALLOW_SHARED_BOT_TOKEN", "").strip().lower()
        if ingest_token and token == ingest_token and allow_shared not in {"1", "true", "yes"}:
            raise RuntimeError(
                "Persistent bot mode cannot share TELEGRAM_TOKEN with ingestion. "
                "Configure PUBLISH_BOT_TOKEN or explicitly set HUNTX_ALLOW_SHARED_BOT_TOKEN=true."
            )
        if ingest_token and token == ingest_token:
            logger.warning(
                "[GatherX] Shared bot/ingest token explicitly allowed; Telegram 409 conflicts remain possible."
            )

        self.token = token
        self.api_id = api_id
        self.api_hash = api_hash

        self.data_dir = str(paths.DATA_DIR)
        self.db_path = str(paths.STATE_DB_PATH)

        self.artifact_store = ArtifactStore()
        self.db = open_db(paths.STATE_DB_PATH)
        self.repo = StateRepo(self.db)

        self._init_tables()
        self._user_cooldowns: Dict[int, float] = OrderedDict()

        session_path = paths.DATA_DIR / "bot.session"
        self.client = TelegramClient(str(session_path), self.api_id, self.api_hash)

    def _init_tables(self):
        with self.db.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_users (
                    user_id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    username TEXT,
                    registered_at REAL NOT NULL,
                    approved INTEGER NOT NULL DEFAULT 0,
                    muted INTEGER DEFAULT 0,
                    last_delivered_at REAL DEFAULT 0,
                    default_format TEXT DEFAULT 'npvt'
                )
                """)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(bot_users)").fetchall()}
            if "approved" not in columns:
                conn.execute("ALTER TABLE bot_users " "ADD COLUMN approved INTEGER NOT NULL DEFAULT 0")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_delivery_checkpoint (
                    user_id TEXT PRIMARY KEY,
                    attempted INTEGER NOT NULL DEFAULT 0,
                    sent INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    updated_at REAL NOT NULL DEFAULT 0
                )
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_delivery_items (
                    user_id TEXT NOT NULL,
                    artifact_hash TEXT NOT NULL,
                    artifact_name TEXT NOT NULL,
                    delivered_at REAL NOT NULL,
                    PRIMARY KEY (user_id, artifact_hash),
                    FOREIGN KEY (user_id)
                        REFERENCES bot_users(user_id) ON DELETE CASCADE
                )
                """)

    def _register_user(self, user_id: str, chat_id: str, username: Optional[str] = None) -> bool:
        with self.db.connect() as conn:
            existing = conn.execute("SELECT 1 FROM bot_users WHERE user_id = ?", (user_id,)).fetchone()
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
        with self.db.connect() as conn:
            return conn.execute("""
                SELECT user_id, chat_id FROM bot_users
                WHERE approved = 1 AND muted = 0
                """).fetchall()

    def _get_user_count(self) -> dict:
        with self.db.connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM bot_users").fetchone()["c"]
            active = conn.execute("SELECT COUNT(*) AS c FROM bot_users " "WHERE approved = 1 AND muted = 0").fetchone()[
                "c"
            ]
            return {"total": total, "active": active, "muted": total - active}

    def _get_user_pref(self, user_id: str) -> str:
        with self.db.connect() as conn:
            row = conn.execute("SELECT default_format FROM bot_users WHERE user_id = ?", (user_id,)).fetchone()
            return row["default_format"] if row and row["default_format"] else "npvt"

    def _set_user_pref(self, user_id: str, fmt: str):
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE bot_users SET default_format = ? WHERE user_id = ?",
                (fmt, user_id),
            )

    def _get_user_info(self, user_id: str) -> Optional[dict]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM bot_users WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def _prune_cooldowns(self, now: float) -> None:
        stale_before = now - self._COOLDOWN_TTL_SECONDS
        for user_id, timestamp in list(self._user_cooldowns.items()):
            if timestamp < stale_before:
                self._user_cooldowns.pop(user_id, None)
        while len(self._user_cooldowns) > self._COOLDOWN_MAX_ENTRIES:
            self._user_cooldowns.pop(next(iter(self._user_cooldowns)), None)

    async def _check_rate_limit(self, event: Any, cooldown_seconds: float = 5) -> bool:
        user_id = getattr(event, "sender_id", None)
        if not user_id or self._is_admin(str(user_id)):
            return True

        now = time.time()
        self._prune_cooldowns(now)
        last_time = self._user_cooldowns.get(user_id, 0.0)
        elapsed = now - last_time
        if elapsed < cooldown_seconds:
            wait_time = max(1, int(cooldown_seconds - elapsed) + 1)
            message = f"⚠️ Slow down. Please wait {wait_time}s before trying again."
            answer = getattr(event, "answer", None)
            if callable(answer):
                await answer(message, alert=True)
            else:
                await event.respond(message)
            return False

        self._user_cooldowns[user_id] = now
        self._user_cooldowns.move_to_end(user_id)
        self._prune_cooldowns(now)
        return True

    @staticmethod
    def _callback_cooldown(data: str) -> float:
        if data.startswith("get:"):
            return 8.0
        if data.startswith(("setfmt:", "cmd:")):
            return 3.0
        return 5.0

    async def _on_callback(self, event: Any) -> None:
        try:
            data = event.data.decode("utf-8", errors="strict") if event.data else ""
            user_id = str(event.sender_id)
            chat_id = event.chat_id

            if data.startswith("admin:"):
                sender = await event.get_sender()
                username = getattr(sender, "username", None)
                if not self._is_admin(user_id, username):
                    await event.answer("❌ Access denied", alert=True)
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
                    await event.answer("Unknown admin action", alert=True)
                return

            if not await self._check_rate_limit(event, self._callback_cooldown(data)):
                return

            if data.startswith("get:"):
                fmt = data.split(":", 1)[1]
                if fmt not in _ALL_VALID_FORMATS:
                    await event.answer("Unknown format", alert=True)
                    return
                await event.answer(f"Fetching {fmt}...")
                await self._send_format_to_user(chat_id, fmt)
                return

            if data.startswith("setfmt:"):
                fmt = data.split(":", 1)[1]
                if fmt not in _ALL_VALID_FORMATS:
                    await event.answer("Unknown format", alert=True)
                    return
                self._set_user_pref(user_id, fmt)
                label = _FORMAT_LABELS.get(fmt, fmt)
                await event.answer(f"Default set to {fmt} ✅")
                await event.edit(
                    f"⚙️ **Set Default Format**\n\nCurrent: `{fmt}` ({label})\n\nPick below or type `/setformat <format>`:",
                    parse_mode="md",
                    buttons=self._build_setformat_keyboard(user_id),
                )
                return

            if data.startswith("cmd:"):
                cmd = data.split(":", 1)[1]
                if cmd == "formats":
                    await event.answer()
                    await self._respond_formats(chat_id)
                elif cmd == "myinfo":
                    await event.answer()
                    await self._respond_myinfo(chat_id, user_id, event=event)
                elif cmd in {"mute", "unmute"}:
                    self._register_user(user_id, str(chat_id))
                    muted = 1 if cmd == "mute" else 0
                    with self.db.connect() as conn:
                        conn.execute("UPDATE bot_users SET muted = ? WHERE user_id = ?", (muted, user_id))
                    await event.answer("Auto-delivery paused 🔇" if muted else "Auto-delivery resumed 🔔")
                    await self._respond_myinfo(chat_id, user_id, event=event)
                elif cmd == "setformat":
                    await event.answer()
                    current = self._get_user_pref(user_id)
                    label = _FORMAT_LABELS.get(current, current)
                    await event.edit(
                        f"⚙️ **Set Default Format**\n\nCurrent: `{current}` ({label})\n\nPick a new default format:",
                        parse_mode="md",
                        buttons=self._build_setformat_keyboard(user_id),
                    )
                else:
                    await event.answer("Unknown action", alert=True)
                return

            await event.answer("Unknown action", alert=True)
        except UnicodeDecodeError:
            logger.warning("[GatherX] Rejected non-UTF-8 callback payload")
            await event.answer("Invalid action", alert=True)
        except Exception:
            logger.exception("[GatherX] Callback failed")
            await event.answer("The request failed. Please try again later.", alert=True)

    async def start(self):
        await self.client.start(bot_token=self.token)

        try:
            if SetBotCommandsRequest is not None and BotCommandScopeDefault is not None:
                await self.client(
                    SetBotCommandsRequest(
                        scope=BotCommandScopeDefault(),
                        lang_code="",
                        commands=_BOT_COMMANDS,
                    )
                )
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

    def _get_system_stats(self) -> dict:
        with self.db.connect() as conn:
            sources = conn.execute("SELECT COUNT(*) AS c FROM source_state").fetchone()["c"]
            files = conn.execute("SELECT COUNT(*) AS c FROM seen_files").fetchone()["c"]
            records = conn.execute("SELECT COUNT(*) AS c FROM records WHERE is_active=1").fetchone()["c"]
            return {"sources": sources, "files": files, "records": records}

    def _get_protocol_counts(self) -> Dict[str, int]:
        from ..formats.npvt import _PROXY_SCHEMES

        counts: Dict[str, int] = {}
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT record_type, COUNT(*) as c FROM records WHERE is_active=1 AND record_type != 'npvt' GROUP BY record_type"
            ).fetchall()
            for r in rows:
                counts[r["record_type"]] = r["c"]

            case_clauses = []
            params = []
            for scheme in _PROXY_SCHEMES:
                proto = scheme.replace("://", "")
                case_clauses.append(
                    "WHEN json_valid(data_json) = 1 AND LOWER(json_extract(data_json, '$.line')) LIKE ? THEN ?"
                )
                params.extend([f"{scheme.lower()}%", proto])

            case_sql = f"""
                SELECT
                    CASE
                        {' '.join(case_clauses)}
                        ELSE 'other'
                    END as sub_proto,
                    COUNT(*) as c
                FROM records
                WHERE is_active=1 AND record_type = 'npvt'
                GROUP BY sub_proto
            """

            rows = conn.execute(case_sql, params).fetchall()
            for r in rows:
                sub_proto = r["sub_proto"]
                counts[sub_proto] = counts.get(sub_proto, 0) + r["c"]

        return counts


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
