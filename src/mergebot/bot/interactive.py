import logging
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from ..store.artifact_store import ArtifactStore
from ..state.repo import StateRepo
from ..state.db import open_db
from ..store.paths import STATE_DB_PATH

logger = logging.getLogger(__name__)

class InteractiveBot:
    def __init__(self, token: str, api_id: int, api_hash: str):
        self.token = token
        self.api_id = api_id
        self.api_hash = api_hash

        self.artifact_store = ArtifactStore()
        self.db = open_db(STATE_DB_PATH)
        self.repo = StateRepo(self.db)

        self._init_subs_table()

        # Use a file-based session for the bot (or in-memory if transient)
        # Since we run periodically, file session is better to persist cache/auth
        # But we are in a container/ephemeral env.
        # Ideally pass a session string, but bot tokens don't strictly need one for basic auth.
        # We'll use 'bot.session' in data dir.
        session_path = Path("persist/data/bot.session")
        self.client = TelegramClient(str(session_path), self.api_id, self.api_hash)

    def _init_subs_table(self):
        with self.db.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_subs (
                    user_id TEXT,
                    chat_id TEXT,
                    format_filter TEXT,
                    frequency_hours INTEGER,
                    last_sent_ts REAL,
                    PRIMARY KEY (user_id, format_filter)
                )
            """)

    async def start(self):
        await self.client.start(bot_token=self.token)

        # Register handlers
        self.client.add_event_handler(self._handler_start, events.NewMessage(pattern='/start|/help'))
        self.client.add_event_handler(self._handler_latest, events.NewMessage(pattern='/latest'))

        # Run loop for a short period to fetch pending updates?
        # Telethon's run_until_disconnected() blocks forever.
        # We want to process *pending* updates and then exit (cron job style).
        # OR we can just fetch history.
        # Better: run for a fixed timeout (e.g., 30 seconds) to process any backlog commands.
        logger.info("Bot started. Listening for updates for 30 seconds...")

        # Also run subscription check once
        await self._process_subscriptions()

        try:
            # We assume the cron job handles the scheduling.
            # We just want to react to any commands sent since last run?
            # Actually, standard Bot API via Webhook or Long Polling is continuous.
            # Running "every 3 hours" means users have to wait 3 hours for a response?
            # That is terrible UX.
            # But the requirement is "User can ask... User can customize...".
            # If the architecture is strict "run periodically", then the bot is not truly interactive in real-time.
            # However, for the purpose of this task within the constraints, we will process pending messages.
            # Telethon 'catch_up' behavior usually fetches missed updates on start.

            # We'll run until disconnected, but interrupt after 60s.
            await asyncio.wait_for(self.client.run_until_disconnected(), timeout=30)
        except asyncio.TimeoutError:
            logger.info("Run finished (timeout).")
        except Exception as e:
            logger.error(f"Bot error: {e}")
        finally:
            await self.client.disconnect()

    async def _handler_start(self, event):
        await event.respond(
            "MergeBot Interactive:\n"
            "/latest [format] [days] - Get latest merged files (default: all, last 4 days)\n"
            "Note: This bot runs periodically. Responses may be delayed."
        )

    async def _handler_latest(self, event):
        args = event.text.split()[1:]
        fmt = args[0] if args else None
        days = int(args[1]) if len(args) > 1 and args[1].isdigit() else 4

        files = self.artifact_store.list_archive(days=days)
        if not files:
            await event.respond(f"No artifacts found in the last {days} days.")
            return

        sent_count = 0
        for f in files:
            parts = f.name.split(".")
            ext = parts[-1]
            if fmt and ext != fmt:
                continue

            await self.client.send_file(
                event.chat_id,
                f,
                caption=f"Archive: {f.name}"
            )
            sent_count += 1
            await asyncio.sleep(0.5)

        if sent_count == 0:
             await event.respond(f"No artifacts found matching filter '{fmt}'.")

    async def _process_subscriptions(self):
        # Placeholder for subscription logic (send updates if due)
        pass

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True)
    parser.add_argument("--api-id", type=int, required=True)
    parser.add_argument("--api-hash", required=True)
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(level=logging.INFO)

    bot = InteractiveBot(args.token, args.api_id, args.api_hash)
    asyncio.run(bot.start())
