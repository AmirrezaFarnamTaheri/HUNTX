import asyncio
import logging
import time

from telethon import TelegramClient, events
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault

from ..store.artifact_store import ArtifactStore
from ..state.repo import StateRepo
from ..state.db import open_db
from ..store.paths import STATE_DB_PATH, DATA_DIR

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "**MergeBot** — Aggregated proxy config publisher\n\n"
    "**Commands:**\n"
    "`/start` `/help` — Show this message\n"
    "`/latest [format] [days]` — Get latest merged files (default: all, 4 days)\n"
    "`/status` — Show pipeline statistics\n"
    "`/run` — Show last pipeline run info\n"
    "`/formats` — List supported formats\n"
    "`/subscribe <format> [hours]` — Auto-deliver every N hours (default: 6)\n"
    "`/unsubscribe [format]` — Remove a subscription\n"
    "`/clean` — Show cleanup instructions\n\n"
    "_This bot runs periodically. Responses may be delayed up to the schedule interval._"
)

_BOT_COMMANDS = [
    BotCommand(command="start", description="Show help message"),
    BotCommand(command="latest", description="Get latest merged files"),
    BotCommand(command="status", description="Show pipeline statistics"),
    BotCommand(command="run", description="Show last pipeline run info"),
    BotCommand(command="formats", description="List supported formats"),
    BotCommand(command="subscribe", description="Auto-deliver a format"),
    BotCommand(command="unsubscribe", description="Remove a subscription"),
    BotCommand(command="clean", description="Show cleanup instructions"),
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
    "opaque_bundle",
]


class InteractiveBot:
    def __init__(self, token: str, api_id: int, api_hash: str):
        self.token = token
        self.api_id = api_id
        self.api_hash = api_hash

        self.artifact_store = ArtifactStore()
        self.db = open_db(STATE_DB_PATH)
        self.repo = StateRepo(self.db)

        self._init_subs_table()

        session_path = DATA_DIR / "bot.session"
        self.client = TelegramClient(str(session_path), self.api_id, self.api_hash)

    def _init_subs_table(self):
        with self.db.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_subs (
                    user_id TEXT,
                    chat_id TEXT,
                    format_filter TEXT,
                    frequency_hours INTEGER DEFAULT 6,
                    last_sent_ts REAL DEFAULT 0,
                    PRIMARY KEY (user_id, format_filter)
                )
                """
            )

    async def start(self, timeout: int = 0):
        """Start the bot. timeout=0 means run forever (persistent mode)."""
        await self.client.start(bot_token=self.token)

        # Register command menu in Telegram
        try:
            await self.client(SetBotCommandsRequest(
                scope=BotCommandScopeDefault(),
                lang_code="",
                commands=_BOT_COMMANDS,
            ))
            logger.info("Bot commands menu registered.")
        except Exception as e:
            logger.warning(f"Failed to register bot commands: {e}")

        self.client.add_event_handler(self._on_start, events.NewMessage(pattern=r"/start|/help"))
        self.client.add_event_handler(self._on_latest, events.NewMessage(pattern=r"/latest"))
        self.client.add_event_handler(self._on_status, events.NewMessage(pattern=r"/status"))
        self.client.add_event_handler(self._on_run, events.NewMessage(pattern=r"/run"))
        self.client.add_event_handler(self._on_formats, events.NewMessage(pattern=r"/formats"))
        self.client.add_event_handler(self._on_subscribe, events.NewMessage(pattern=r"/subscribe"))
        self.client.add_event_handler(self._on_unsubscribe, events.NewMessage(pattern=r"/unsubscribe"))
        self.client.add_event_handler(self._on_clean, events.NewMessage(pattern=r"/clean"))

        mode = "persistent" if timeout == 0 else f"{timeout}s window"
        logger.info(f"Bot started ({mode}). Delivering subscriptions...")

        await self._deliver_subscriptions()

        try:
            if timeout > 0:
                await asyncio.wait_for(self.client.run_until_disconnected(), timeout=timeout)
            else:
                await self.client.run_until_disconnected()
        except asyncio.TimeoutError:
            logger.info("Bot timeout reached — exiting.")
        except Exception as e:
            logger.error(f"Bot error: {e}")
        finally:
            await self.client.disconnect()

    # ── Handlers ──────────────────────────────────────────────────────

    async def _on_start(self, event):
        await event.respond(HELP_TEXT, parse_mode="md")

    async def _on_latest(self, event):
        args = event.text.split()[1:]
        fmt = args[0] if args else None
        days = int(args[1]) if len(args) > 1 and args[1].isdigit() else 4

        files = self.artifact_store.list_archive(days=days)
        if not files:
            await event.respond(f"No artifacts in the last {days} day(s).")
            return

        sent = 0
        for f in files:
            ext = f.suffix.lstrip(".")
            if fmt and ext != fmt:
                continue
            await self.client.send_file(event.chat_id, f, caption=f"`{f.name}`", parse_mode="md")
            sent += 1
            await asyncio.sleep(0.5)

        if sent == 0:
            await event.respond(f"No artifacts matching `{fmt}`.")

    async def _on_status(self, event):
        try:
            with self.db.connect() as conn:
                total = conn.execute("SELECT COUNT(*) AS c FROM seen_files").fetchone()["c"]
                pending = conn.execute("SELECT COUNT(*) AS c FROM seen_files WHERE status='pending'").fetchone()["c"]
                processed = conn.execute("SELECT COUNT(*) AS c FROM seen_files WHERE status='processed'").fetchone()[
                    "c"
                ]
                failed = conn.execute("SELECT COUNT(*) AS c FROM seen_files WHERE status='failed'").fetchone()["c"]
                sources = conn.execute("SELECT COUNT(*) AS c FROM source_state").fetchone()["c"]
                records = conn.execute("SELECT COUNT(*) AS c FROM records WHERE is_active=1").fetchone()["c"]

            msg = (
                f"**Pipeline Status**\n"
                f"Sources: {sources}\n"
                f"Files: {total} total ({pending} pending, {processed} processed, {failed} failed)\n"
                f"Records: {records} active"
            )
            await event.respond(msg, parse_mode="md")
        except Exception as e:
            await event.respond(f"Error: {e}")

    async def _on_run(self, event):
        """Show last pipeline run info per source."""
        try:
            import json as _json
            with self.db.connect() as conn:
                rows = conn.execute(
                    "SELECT source_id, state_json FROM source_state ORDER BY updated_at DESC LIMIT 20"
                ).fetchall()

            if not rows:
                await event.respond("No pipeline run data yet.")
                return

            lines = ["**Last Pipeline Run (per source):**"]
            for row in rows:
                sid = row["source_id"]
                try:
                    st = _json.loads(row["state_json"])
                    lr = st.get("stats", {}).get("last_run", {})
                    if lr:
                        files = lr.get("files_ingested", "?")
                        skipped = lr.get("skipped_files", "?")
                        dur = lr.get("duration_seconds", "?")
                        byt = lr.get("bytes_ingested", 0)
                        kb = f"{byt / 1024:.1f}" if isinstance(byt, (int, float)) else "?"
                        lines.append(
                            f"`{sid}`: {files} new, {skipped} skipped, "
                            f"{kb} KB, {dur}s"
                        )
                    else:
                        lines.append(f"`{sid}`: no run data")
                except Exception:
                    lines.append(f"`{sid}`: parse error")

            await event.respond("\n".join(lines), parse_mode="md")
        except Exception as e:
            await event.respond(f"Error: {e}")

    async def _on_clean(self, event):
        """Show cleanup instructions."""
        msg = (
            "**Cleanup Instructions**\n\n"
            "To wipe all data, state, and cache for a fresh start, run:\n\n"
            "`mergebot clean`\n\n"
            "Or with auto-confirm:\n"
            "`mergebot clean --yes`\n\n"
            "This deletes: raw store, output, archive, state DB, rejects, and logs."
        )
        await event.respond(msg, parse_mode="md")

    async def _on_formats(self, event):
        lines = ["**Supported Formats:**"] + [f"• `{f}`" for f in SUPPORTED_FORMATS]
        await event.respond("\n".join(lines), parse_mode="md")

    async def _on_subscribe(self, event):
        args = event.text.split()[1:]
        if not args:
            await event.respond("Usage: `/subscribe <format> [hours]`", parse_mode="md")
            return
        fmt = args[0]
        hours = int(args[1]) if len(args) > 1 and args[1].isdigit() else 6
        user_id = str(event.sender_id)
        chat_id = str(event.chat_id)

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_subs (user_id, chat_id, format_filter, frequency_hours, last_sent_ts)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(user_id, format_filter) DO UPDATE SET
                    frequency_hours = excluded.frequency_hours, chat_id = excluded.chat_id
                """,
                (user_id, chat_id, fmt, hours),
            )
        await event.respond(f"Subscribed to `{fmt}` every {hours}h.", parse_mode="md")

    async def _on_unsubscribe(self, event):
        args = event.text.split()[1:]
        user_id = str(event.sender_id)
        with self.db.connect() as conn:
            if args:
                conn.execute("DELETE FROM bot_subs WHERE user_id=? AND format_filter=?", (user_id, args[0]))
                await event.respond(f"Unsubscribed from `{args[0]}`.", parse_mode="md")
            else:
                conn.execute("DELETE FROM bot_subs WHERE user_id=?", (user_id,))
                await event.respond("All subscriptions removed.")

    # ── Subscription delivery ─────────────────────────────────────────

    async def _deliver_subscriptions(self):
        now = time.time()
        try:
            with self.db.connect() as conn:
                rows = conn.execute("SELECT * FROM bot_subs").fetchall()

            for row in rows:
                freq_sec = row["frequency_hours"] * 3600
                if now - row["last_sent_ts"] < freq_sec:
                    continue

                fmt = row["format_filter"]
                chat_id = row["chat_id"]
                files = self.artifact_store.list_archive(days=1)
                sent = False
                for f in files:
                    if f.suffix.lstrip(".") == fmt:
                        await self.client.send_file(
                            int(chat_id), f, caption=f"Subscription: `{f.name}`", parse_mode="md"
                        )
                        sent = True
                        break

                if sent:
                    with self.db.connect() as conn:
                        conn.execute(
                            "UPDATE bot_subs SET last_sent_ts=? WHERE user_id=? AND format_filter=?",
                            (now, row["user_id"], fmt),
                        )
        except Exception as e:
            logger.error(f"Subscription delivery error: {e}")


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
