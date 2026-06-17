import asyncio
import logging
import time
import datetime
from pathlib import Path
from typing import Optional, List
from ..store import paths
from .constants import _AUTO_DELIVER_FORMATS, _FORMAT_LABELS, _ALL_VALID_FORMATS

logger = logging.getLogger(__name__)


class DeliveryMixin:
    # These methods are designed to be mixed into InteractiveBot.
    # The InteractiveBot class will provide self.client, self.db, self.repo, and self.artifact_store.  # type: ignore[attr-defined]

    async def deliver_updates(self):
        """Connect, auto-send latest outputs to all registered users, disconnect.
        Called automatically after every pipeline run."""
        try:
            await self.client.start(bot_token=self.token)  # type: ignore[attr-defined]
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
                    await self.client.send_message(  # type: ignore[attr-defined]
                        chat_id,
                        "🛰 **GatherX Update**\n"
                        f"Fresh proxy configs — {len(files_to_send)} file(s):",
                        parse_mode="md",
                    )
                    for fpath, caption in files_to_send:
                        await self.client.send_file(chat_id, fpath, caption=caption, parse_mode="md")  # type: ignore[attr-defined]
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
                await self.client.disconnect()  # type: ignore[attr-defined]
            except Exception as e:
                logger.debug(f"[GatherX] Failed to disconnect bot client: {e}")
            # Allow Telethon internal tasks to finish cancellation
            await asyncio.sleep(0.25)

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
                await self.client.send_message(  # type: ignore[attr-defined]
                    chat_id,
                    "🛰 **GatherX Update**\n"
                    f"Fresh proxy configs — {len(files_to_send)} file(s):",
                    parse_mode="md",
                )
                for fpath, caption in files_to_send:
                    await self.client.send_file(chat_id, fpath, caption=caption, parse_mode="md")  # type: ignore[attr-defined]
                    await asyncio.sleep(0.3)

                with self.db.connect() as conn:
                    conn.execute(
                        "UPDATE bot_users SET last_delivered_at = ? WHERE user_id = ?",
                        (now, user["user_id"]),
                    )
            except Exception as e:
                logger.warning(f"[GatherX] Failed to deliver to {user['user_id']}: {e}")

    def _collect_delivery_files(self, output_dir: Path, formats=None) -> List[tuple]:
        """Collect output files to deliver. Returns list of (path, caption).
        If formats is given, only include files whose name ends with one of those suffixes.
        If formats is None, uses _AUTO_DELIVER_FORMATS."""
        allowed = formats or _AUTO_DELIVER_FORMATS
        results: list[tuple] = []
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

    async def _send_format_to_user(self, chat_id: int, fmt: str):
        """Send files matching a format to a user. Used by both /get and button callbacks."""
        if fmt not in _ALL_VALID_FORMATS:
            await self.client.send_message(  # type: ignore[attr-defined]
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
                    await self.client.send_file(  # type: ignore[attr-defined]
                        chat_id, f,
                        caption=f"{label}\n`{f.name}` ({size_kb:.0f} KB)",
                        parse_mode="md",
                    )
                    sent += 1
                    await asyncio.sleep(0.3)

        if sent == 0:
            sent = await self._send_latest_to_user(chat_id, fmt=fmt, days=4)

        if sent == 0:
            await self.client.send_message(  # type: ignore[attr-defined]
                chat_id,
                f"No files found for `{fmt}`.\n"
                f"The pipeline may not have produced this format yet.\n"
                f"Use /formats to see all options.",
                parse_mode="md",
            )

    async def _send_latest_to_user(self, chat_id: int, fmt: Optional[str] = None, days: int = 4):
        """Send latest artifacts to a user, optionally filtered by format."""
        files = self.artifact_store.list_archive(days=days)  # type: ignore[attr-defined]
        if not files:
            await self.client.send_message(chat_id, f"No artifacts in the last {days} day(s).")  # type: ignore[attr-defined]
            return 0

        sent = 0
        for f in files:
            if fmt and not f.name.endswith(f".{fmt}"):
                continue
            size_kb = f.stat().st_size / 1024
            await self.client.send_file(  # type: ignore[attr-defined]
                chat_id, f,
                caption=f"`{f.name}` ({size_kb:.0f} KB)",
                parse_mode="md",
            )
            sent += 1
            await asyncio.sleep(0.3)

        if sent == 0 and fmt:
            await self.client.send_message(chat_id, f"No artifacts matching `{fmt}`.")  # type: ignore[attr-defined]
        return sent
