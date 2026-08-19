import asyncio
import logging
import os
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

try:
    from telethon import Button, TelegramClient, events
    from telethon.tl.functions.bots import SetBotCommandsRequest
    from telethon.tl.types import BotCommand, BotCommandScopeDefault
except ModuleNotFoundError:  # pragma: no cover
    TelegramClient = None  # type: ignore[assignment]
    events = None  # type: ignore[assignment]
    Button = None  # type: ignore[assignment]
    SetBotCommandsRequest = None  # type: ignore[assignment]
    BotCommand = None  # type: ignore[assignment]
    BotCommandScopeDefault = None  # type: ignore[assignment]

from ..state.db import open_db
from ..state.repo import StateRepo
from ..store import paths
from ..store.artifact_store import ArtifactStore
from .admin import AdminMixin
from .constants import _ALL_VALID_FORMATS, _BOT_COMMANDS, _FORMAT_LABELS
from .constants import SUPPORTED_FORMATS as SUPPORTED_FORMATS  # noqa: F401
from .constants import WELCOME_TEXT as WELCOME_TEXT  # noqa: F401
from .delivery import DeliveryMixin
from .handlers import HandlersMixin

logger = logging.getLogger(__name__)


class InteractiveBot(HandlersMixin, DeliveryMixin, AdminMixin):
    """Persistent GatherX Telegram bot backed by the canonical HUNTX state DB."""

    _COOLDOWN_MAX_ENTRIES = 4096
    _COOLDOWN_TTL_SECONDS = 3600.0

    def __init__(self, token: str, api_id: int, api_hash: str):
        """Initialize bot dependencies, state access, and the Telegram client."""
        if TelegramClient is None:
            raise RuntimeError(
                "Telethon is required to run the bot. Install dependencies (pip install -e .)."
            )

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
        """Verify the canonical schema applied by ``open_db``.

        Table creation and migrations live exclusively in ``schema.sql`` and
        ``DBConnection._check_migrations``. Duplicating DDL here previously let
        bot startup drift independently from CLI reset/restore and migrations.
        """
        required_tables = {
            "bot_users",
            "bot_delivery_checkpoint",
            "bot_delivery_items",
        }
        required_user_columns = {
            "user_id",
            "chat_id",
            "username",
            "registered_at",
            "approved",
            "muted",
            "last_delivered_at",
            "default_format",
        }
        with self.db.connect() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            missing_tables = required_tables - tables
            if missing_tables:
                raise RuntimeError(
                    f"Canonical bot schema is incomplete; missing tables: {sorted(missing_tables)}"
                )

            user_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(bot_users)").fetchall()
            }
            missing_columns = required_user_columns - user_columns
            if missing_columns:
                raise RuntimeError(
                    "Canonical bot_users schema is incomplete; missing columns: "
                    f"{sorted(missing_columns)}"
                )

    def _register_user(
        self,
        user_id: str,
        chat_id: str,
        username: Optional[str] = None,
    ) -> bool:
        """Create/refresh a pending private-chat user without erasing names."""
        user_id = str(user_id)
        chat_id = str(chat_id)
        if chat_id != user_id:
            logger.warning(
                "[Security] Refusing GatherX registration/chat reassignment for user=%s chat=%s; "
                "artifact delivery is private-chat only",
                user_id,
                chat_id,
            )
            return False

        with self.db.connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM bot_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE bot_users
                    SET chat_id = ?, username = COALESCE(?, username)
                    WHERE user_id = ?
                    """,
                    (chat_id, username, user_id),
                )
                return False
            conn.execute(
                "INSERT INTO bot_users (user_id, chat_id, username, registered_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, chat_id, username, time.time()),
            )
            return True

    def _get_active_users(self) -> list:
        """Return approved users whose delivery target is their private chat."""
        with self.db.connect() as conn:
            return conn.execute(
                """
                SELECT user_id, chat_id FROM bot_users
                WHERE approved = 1 AND muted = 0 AND chat_id = user_id
                """
            ).fetchall()

    def _get_user_count(self) -> dict:
        """Return total, safely active, and explicitly muted bot-user counts."""
        with self.db.connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM bot_users").fetchone()["c"]
            active = conn.execute(
                """
                SELECT COUNT(*) AS c FROM bot_users
                WHERE approved = 1 AND muted = 0 AND chat_id = user_id
                """
            ).fetchone()["c"]
            muted = conn.execute(
                "SELECT COUNT(*) AS c FROM bot_users WHERE muted = 1"
            ).fetchone()["c"]
            return {"total": total, "active": active, "muted": muted}

    def _get_user_pref(self, user_id: str) -> str:
        """Return a user's preferred delivery format, defaulting to ``npvt``."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT default_format FROM bot_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return row["default_format"] if row and row["default_format"] else "npvt"

    def _set_user_pref(self, user_id: str, fmt: str):
        """Persist a user's preferred delivery format."""
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE bot_users SET default_format = ? WHERE user_id = ?",
                (fmt, user_id),
            )

    def _get_user_info(self, user_id: str) -> Optional[dict]:
        """Return one bot-user row as a dictionary, if registered."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM bot_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def _is_user_approved(self, user_id: str) -> bool:
        """Return whether a sender may retrieve protected artifacts."""
        if self._is_admin(str(user_id)):
            return True
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT approved FROM bot_users WHERE user_id = ?",
                (str(user_id),),
            ).fetchone()
        return bool(row and int(row["approved"]) == 1)

    @staticmethod
    def _is_private_event(event: Any) -> bool:
        """Return whether an event is bound to the sender's private chat."""
        sender_id = getattr(event, "sender_id", None)
        chat_id = getattr(event, "chat_id", None)
        if sender_id is None or chat_id is None:
            return False
        declared_private = getattr(event, "is_private", None)
        if declared_private is False:
            return False
        return str(sender_id) == str(chat_id)

    async def _require_private_chat(self, event: Any) -> bool:
        """Reject artifact access from groups/channels even for approved users."""
        if self._is_private_event(event):
            return True
        answer = getattr(event, "answer", None)
        if getattr(event, "data", None) is not None and callable(answer):
            await answer("Use GatherX in a private chat for downloads.", alert=True)
        else:
            await event.respond(
                "🔒 **Private chat required**\nArtifact access is available only in your DM with this bot.",
                parse_mode="md",
            )
        return False

    async def _require_approved(self, event: Any) -> bool:
        """Require both a private chat and operator approval for protected actions."""
        if not await self._require_private_chat(event):
            return False
        user_id = str(getattr(event, "sender_id", "") or "")
        if user_id and self._is_user_approved(user_id):
            return True
        message = (
            "⏳ **Approval required**\n"
            "Your registration is pending administrator approval."
        )
        answer = getattr(event, "answer", None)
        if getattr(event, "data", None) is not None and callable(answer):
            await answer("Approval required. Your registration is still pending.", alert=True)
        else:
            await event.respond(message, parse_mode="md")
        return False

    def _prune_cooldowns(self, now: float) -> None:
        """Remove stale rate-limit entries and enforce the in-memory size bound."""
        stale_before = now - self._COOLDOWN_TTL_SECONDS
        for user_id, timestamp in list(self._user_cooldowns.items()):
            if timestamp < stale_before:
                self._user_cooldowns.pop(user_id, None)
        while len(self._user_cooldowns) > self._COOLDOWN_MAX_ENTRIES:
            self._user_cooldowns.pop(next(iter(self._user_cooldowns)), None)

    async def _check_rate_limit(
        self,
        event: Any,
        cooldown_seconds: float = 5,
    ) -> bool:
        """Apply per-sender command/callback cooldowns while exempting admins."""
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
        """Return the cooldown interval for a callback payload family."""
        if data.startswith("get:"):
            return 8.0
        if data.startswith(("setfmt:", "cmd:")):
            return 3.0
        return 5.0

    async def _on_callback(self, event: Any) -> None:
        """Dispatch validated inline-button callbacks without exposing failures."""
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
                if not await self._require_approved(event):
                    return
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
                    f"⚙️ **Set Default Format**\n\nCurrent: `{fmt}` ({label})\n\n"
                    "Pick below or type `/setformat <format>`:",
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
                        conn.execute(
                            "UPDATE bot_users SET muted = ? WHERE user_id = ?",
                            (muted, user_id),
                        )
                    await event.answer(
                        "Auto-delivery paused 🔇" if muted else "Auto-delivery resumed 🔔"
                    )
                    await self._respond_myinfo(chat_id, user_id, event=event)
                elif cmd == "setformat":
                    await event.answer()
                    current = self._get_user_pref(user_id)
                    label = _FORMAT_LABELS.get(current, current)
                    await event.edit(
                        f"⚙️ **Set Default Format**\n\nCurrent: `{current}` ({label})\n\n"
                        "Pick a new default format:",
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
        """Start the Telegram bot, register commands/handlers, and poll until stopped."""
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
        except Exception as exc:
            logger.warning("[GatherX] Failed to register commands: %s", exc)

        self._register_handlers()
        stats = self._get_user_count()
        logger.info(
            "[GatherX] Bot started (long-polling) — %s users (%s active, %s muted)",
            stats["total"],
            stats["active"],
            stats["muted"],
        )

        try:
            await self.client.run_until_disconnected()
        except Exception as exc:
            logger.error("[GatherX] Bot error: %s", exc)
        finally:
            await self.client.disconnect()

    def _get_system_stats(self) -> dict:
        """Return aggregate source, seen-file, and active-record counts."""
        with self.db.connect() as conn:
            sources = conn.execute("SELECT COUNT(*) AS c FROM source_state").fetchone()["c"]
            files = conn.execute("SELECT COUNT(*) AS c FROM seen_files").fetchone()["c"]
            records = conn.execute(
                "SELECT COUNT(*) AS c FROM records WHERE is_active=1"
            ).fetchone()["c"]
            return {"sources": sources, "files": files, "records": records}

    def _get_protocol_counts(self) -> Dict[str, int]:
        """Return active record counts grouped by protocol or URI scheme."""
        from ..formats.npvt import _REPORT_PROXY_SCHEMES

        counts: Dict[str, int] = {}
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT record_type, COUNT(*) as c FROM records "
                "WHERE is_active=1 AND record_type != 'npvt' GROUP BY record_type"
            ).fetchall()
            for row in rows:
                counts[row["record_type"]] = row["c"]

            case_clauses = []
            params = []
            for scheme in _REPORT_PROXY_SCHEMES:
                proto = scheme.replace("://", "")
                case_clauses.append(
                    "WHEN json_valid(data_json) = 1 AND "
                    "LOWER(json_extract(data_json, '$.line')) LIKE ? THEN ?"
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
            for row in rows:
                sub_proto = row["sub_proto"]
                counts[sub_proto] = counts.get(sub_proto, 0) + row["c"]

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
