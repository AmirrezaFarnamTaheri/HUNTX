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

from .constants import (
    WELCOME_TEXT,
    _BOT_COMMANDS,
    SUPPORTED_FORMATS,
    _ALL_VALID_FORMATS,
    _AUTO_DELIVER_FORMATS,
    _FORMAT_LABELS,
)
from .handlers import HandlersMixin
from .delivery import DeliveryMixin
from .admin import AdminMixin

logger = logging.getLogger(__name__)


class InteractiveBot(HandlersMixin, DeliveryMixin, AdminMixin):
    def __init__(self, token: str, api_id: int, api_hash: str):
        if TelegramClient is None:
            raise RuntimeError("Telethon is required to run the bot. Install dependencies (pip install -e .).")
        self.token = token
        self.api_id = api_id
        self.api_hash = api_hash

        self.data_dir = str(paths.DATA_DIR)
        self.db_path = str(paths.STATE_DB_PATH)

        self.artifact_store = ArtifactStore()
        self.db = open_db(paths.STATE_DB_PATH)
        self.repo = StateRepo(self.db)

        self._init_tables()
        self._user_cooldowns: Dict[int, float] = {}

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
            
            # Dynamically build CASE SQL statement using SQLite native JSON support with parameterized inputs
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
                        {" ".join(case_clauses)}
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
