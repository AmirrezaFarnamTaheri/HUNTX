import asyncio
import logging
import os
from typing import Optional

from telethon import Button

from ..store import paths

logger = logging.getLogger(__name__)


class AdminMixin:
    """Restricted administrative commands mixed into ``InteractiveBot``."""

    def _is_admin(self, user_id: str, username: Optional[str] = None) -> bool:
        """Authorize only immutable numeric Telegram user IDs from ``HUNTX_ADMINS``."""
        admins_str = os.environ.get("HUNTX_ADMINS", "")
        if not admins_str:
            return False
        admins = [entry.strip() for entry in admins_str.split(",") if entry.strip()]
        user_id_str = str(user_id).strip()

        for admin_id in admins:
            if not admin_id.isdigit():
                logger.warning(
                    "[Security] Non-numeric admin ID configured in HUNTX_ADMINS: %r. "
                    "Insecure and ignored.",
                    admin_id,
                )

        numeric_admins = {admin_id for admin_id in admins if admin_id.isdigit()}
        return user_id_str in numeric_admins

    async def _require_admin(self, event) -> bool:
        """Authorize an admin command using immutable numeric Telegram user IDs."""
        user_id = str(event.sender_id)
        if self._is_admin(user_id):
            return True
        await event.respond(
            "❌ **Access Denied**\nThis command is restricted to administrators.",
            parse_mode="md",
        )
        return False

    @staticmethod
    def _target_user_id(event) -> Optional[str]:
        """Extract a numeric target user ID from an admin command event."""
        parts = (getattr(event, "text", "") or "").split()
        if len(parts) < 2:
            return None
        target = parts[1].strip()
        return target if target.isdigit() else None

    async def _on_approve(self, event):
        """Approve a registered user for automatic delivery: /approve <user_id>."""
        if not await self._require_admin(event):
            return
        target = self._target_user_id(event)
        if target is None:
            await event.respond("Usage: `/approve <numeric_user_id>`", parse_mode="md")
            return

        with self.db.connect() as conn:
            cursor = conn.execute(
                "UPDATE bot_users SET approved = 1 WHERE user_id = ?",
                (target,),
            )
        if cursor.rowcount == 0:
            await event.respond(f"No registered user `{target}` was found.", parse_mode="md")
            return
        await event.respond(
            f"✅ User `{target}` approved for automatic delivery.",
            parse_mode="md",
        )

    async def _on_deny(self, event):
        """Revoke/deny automatic delivery approval: /deny <user_id>."""
        if not await self._require_admin(event):
            return
        target = self._target_user_id(event)
        if target is None:
            await event.respond("Usage: `/deny <numeric_user_id>`", parse_mode="md")
            return

        with self.db.connect() as conn:
            cursor = conn.execute(
                "UPDATE bot_users SET approved = 0 WHERE user_id = ?",
                (target,),
            )
        if cursor.rowcount == 0:
            await event.respond(f"No registered user `{target}` was found.", parse_mode="md")
            return
        await event.respond(
            f"🚫 User `{target}` is not approved for automatic delivery.",
            parse_mode="md",
        )

    async def _on_pending(self, event):
        """List registered users awaiting approval: /pending."""
        if not await self._require_admin(event):
            return

        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, username, registered_at
                FROM bot_users
                WHERE approved = 0
                ORDER BY registered_at ASC, user_id ASC
                LIMIT 50
                """
            ).fetchall()
            count_row = conn.execute(
                "SELECT COUNT(*) AS c FROM bot_users WHERE approved = 0"
            ).fetchone()

        total = int(count_row["c"]) if count_row else 0
        if not rows:
            await event.respond("✅ No users are awaiting approval.")
            return

        lines = [f"👥 **Pending approvals:** `{total}`"]
        for row in rows:
            username = row["username"] or "—"
            lines.append(f"- `{row['user_id']}` — @{username}")
        if total > len(rows):
            lines.append(f"… and {total - len(rows)} more")
        await event.respond("\n".join(lines), parse_mode="md")

    async def _on_admin(self, event):
        """Dispatch the secure admin dashboard and supported admin subcommands."""
        user_id = str(event.sender_id)
        sender = await event.get_sender()
        username = getattr(sender, "username", None)

        if not self._is_admin(user_id, username):
            await event.respond(
                "❌ **Access Denied**\nThis command is restricted to administrators.",
                parse_mode="md",
            )
            return

        args = event.text.split()[1:]
        if args:
            sub = args[0].lower()
            if sub == "run":
                await self._trigger_background_run(event)
                return
            if sub == "prune":
                days = 30
                if len(args) > 1 and args[1].isdigit():
                    days = int(args[1])
                await self._perform_admin_prune(event, days)
                return

        await self._respond_admin_dashboard(event)

    async def _respond_admin_dashboard(self, event, edit=False):
        """Send or refresh the restricted administrative status dashboard."""
        users = self._get_user_count()
        system = self._get_system_stats()
        with self.db.connect() as conn:
            pending_row = conn.execute(
                "SELECT COUNT(*) AS c FROM bot_users WHERE approved = 0"
            ).fetchone()
        pending = int(pending_row["c"]) if pending_row else 0

        msg = (
            "🛠 **GatherX Restricted Admin Panel**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 **Users:** `{users['total']}` "
            f"(`{users['active']}` active, `{users['muted']}` muted)\n"
            f"🕓 **Pending approvals:** `{pending}`\n"
            f"📡 **Sources:** `{system['sources']}`\n"
            f"📄 **Seen Files:** `{system['files']}`\n"
            f"💎 **Active Records:** `{system['records']}`\n"
            "\nApproval commands: `/pending`, `/approve <id>`, `/deny <id>`"
        )

        buttons = [
            [Button.inline("⚡ Trigger Pipeline Run", b"admin:run")],
            [
                Button.inline("🧹 Prune Database (30 Days)", b"admin:prune:30"),
                Button.inline("🧹 Prune Database (15 Days)", b"admin:prune:15"),
            ],
            [Button.inline("📊 Refresh Stats", b"admin:stats")],
        ]

        if edit:
            await event.edit(msg, parse_mode="md", buttons=buttons)
        else:
            await event.respond(msg, parse_mode="md", buttons=buttons)

    async def _trigger_background_run(self, event):
        """Trigger at most one background pipeline run at a time."""
        current_task = getattr(self, "_pipeline_task", None)
        if current_task is not None and not current_task.done():
            if hasattr(event, "answer"):
                await event.answer("Pipeline is already running.")
            await event.respond(
                "⏳ **Pipeline execution is already in progress.**\n"
                "Wait for the current run to finish before starting another.",
                parse_mode="md",
            )
            return

        loop = asyncio.get_running_loop()

        async def run_pipeline_task():
            """Run the blocking pipeline off-loop, then deliver resulting updates."""
            try:
                await loop.run_in_executor(None, self._run_pipeline_blocking)
                await self.deliver_updates_active()
                await self.client.send_message(
                    event.chat_id,
                    "✅ **Pipeline execution and subscription delivery completed successfully!**",
                    parse_mode="md",
                )
            except Exception as exc:
                logger.exception("Background pipeline run failed: %s", exc)
                await self.client.send_message(
                    event.chat_id,
                    f"❌ **Pipeline execution failed:**\n`{exc}`",
                    parse_mode="md",
                )
            finally:
                self._pipeline_task = None

        self._pipeline_task = asyncio.create_task(run_pipeline_task())

        if hasattr(event, "answer"):
            await event.answer("Starting pipeline run...")
        await event.respond(
            "⚡ **Pipeline execution started in background...**\n"
            "An update will be sent when complete.",
            parse_mode="md",
        )

    def _run_pipeline_blocking(self):
        """Load/validate config and execute one pipeline run under the process lock."""
        from ..config.loader import load_config
        from ..config.validate import validate_config
        from ..core.locks import acquire_lock
        from ..core.orchestrator import Orchestrator

        paths.set_paths(self.data_dir, self.db_path)

        config_path = os.environ.get("HUNTX_CONFIG", "config.yaml")
        config = load_config(config_path)
        validate_config(config)

        lock_path = paths.STATE_DIR / "huntx.lock"
        with acquire_lock(lock_path):
            orchestrator = Orchestrator(config)
            no_publish = os.environ.get("HUNTX_BOT_NO_PUBLISH", "false").lower() == "true"
            orchestrator.run(timeout=16200, no_publish=no_publish)

    async def _perform_admin_prune(self, event, days):
        """Invoke repo and raw-store pruning and report the resulting counts."""
        from ..store.raw_store import RawStore

        if hasattr(event, "answer"):
            await event.answer(f"Pruning database ({days} days)...")

        msg = await event.respond(
            f"🧹 **Pruning database and raw store (older than {days} days)...**",
            parse_mode="md",
        )

        try:
            loop = asyncio.get_running_loop()

            def prune_blocking():
                """Prune DB rows, then delete only raw blobs no longer referenced."""
                raw_store = RawStore()
                result = self.repo.prune_old_data(days)
                raw_pruned = 0
                candidate_hashes = set(result["raw_hashes"])
                if candidate_hashes:
                    live_hashes = self.repo.get_all_known_hashes()
                    orphaned_hashes = sorted(candidate_hashes - live_hashes)
                    if orphaned_hashes:
                        raw_pruned = raw_store.prune_by_hashes(orphaned_hashes)
                return result, raw_pruned

            result, raw_pruned = await loop.run_in_executor(None, prune_blocking)

            report = (
                f"✅ **Pruning Complete (Older than {days} days)**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📄 **Seen Files Pruned:** `{result.get('seen_files', 0)}`\n"
                f"💎 **Records Pruned:** `{result.get('records', 0)}`\n"
                f"📦 **Published Artifacts Pruned:** "
                f"`{result.get('published_artifacts', 0)}`\n"
                f"🧹 **Raw Disk Blobs Deleted:** `{raw_pruned}`"
            )
            await msg.edit(report, parse_mode="md")

        except Exception as exc:
            logger.exception("Admin pruning failed: %s", exc)
            await msg.edit(
                f"❌ **Pruning Failed:**\n`{exc}`",
                parse_mode="md",
            )
