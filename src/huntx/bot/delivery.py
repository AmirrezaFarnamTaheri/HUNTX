import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, List, Optional

try:
    from telethon.errors import FloodWaitError
except ModuleNotFoundError:  # pragma: no cover

    class FloodWaitError(Exception):
        seconds = 0


from ..store import paths
from .constants import _AUTO_DELIVER_FORMATS, _FORMAT_LABELS, _ALL_VALID_FORMATS

logger = logging.getLogger(__name__)


class DeliveryMixin:
    async def send_freshness_alert(
        self,
        admin_chat_id: int,
        proxy_count: int,
        min_threshold: int = 10,
        status_msg: str = "Pipeline Complete",
    ) -> bool:
        """
        Sends an alert notification to the specified admin chat ID.
        """
        try:
            alert_prefix = "⚠️ [LOW FRESHNESS WARNING]" if proxy_count < min_threshold else "✅ [PIPELINE REPORT]"
<<<<<<< Updated upstream
            message = f"{alert_prefix} {status_msg}\nFresh Proxies Available: {proxy_count} (Min Threshold: {min_threshold})"
=======
            message = (
                f"{alert_prefix} {status_msg}\nFresh Proxies Available: {proxy_count} (Min Threshold: {min_threshold})"
            )
>>>>>>> Stashed changes
            if hasattr(self, "client") and self.client:
                await self._send_with_floodwait(self.client.send_message, admin_chat_id, message)
                return True
        except Exception as exc:
            logger.error("[GatherX] Failed to send freshness alert: %s", exc)
        return False

    async def _send_with_floodwait(self, method: Any, *args: Any, **kwargs: Any) -> Any:
        max_wait = max(0, int(os.environ.get("HUNTX_FLOODWAIT_MAX_SECONDS", "60")))
        max_retries = max(0, int(os.environ.get("HUNTX_FLOODWAIT_MAX_RETRIES", "2")))
        retries = 0
        while True:
            try:
                return await method(*args, **kwargs)
            except FloodWaitError as exc:
                delay = int(getattr(exc, "seconds", 0) or 0)
                if delay <= 0 or delay > max_wait or retries >= max_retries:
                    raise
                retries += 1
                logger.warning(
                    "[GatherX] FloodWait %ss; retry %s/%s",
                    delay,
                    retries,
                    max_retries,
                )
                await asyncio.sleep(delay)

    def _record_delivery_checkpoint(
        self,
        user_id: str,
        *,
        attempted: int,
        sent: int,
        failed: int,
        error: Optional[str] = None,
    ) -> None:
        now = time.time()
        with self.db.connect() as conn:  # type: ignore[attr-defined]
            conn.execute(
                """
                INSERT INTO bot_delivery_checkpoint
                    (user_id, attempted, sent, failed, last_error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    attempted=excluded.attempted,
                    sent=excluded.sent,
                    failed=excluded.failed,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (user_id, attempted, sent, failed, error, now),
            )
            if sent > 0:
                conn.execute(
                    "UPDATE bot_users SET last_delivered_at = ? WHERE user_id = ?",
                    (now, user_id),
                )

    async def _deliver_files_to_user(self, user: Any, files_to_send: List[tuple]) -> tuple[int, int]:
        user_id = str(user["user_id"])
        chat_id = int(user["chat_id"])
        sent = 0
        failed = 0
        last_error: Optional[str] = None

        try:
            await self._send_with_floodwait(
                self.client.send_message,  # type: ignore[attr-defined]
                chat_id,
                "🛰 **GatherX Update**\n" f"Fresh proxy configs — {len(files_to_send)} file(s):",
                parse_mode="md",
            )
            for fpath, caption in files_to_send:
                try:
                    await self._send_with_floodwait(
                        self.client.send_file,  # type: ignore[attr-defined]
                        chat_id,
                        fpath,
                        caption=caption,
                        parse_mode="md",
                    )
                    sent += 1
                except Exception as exc:
                    failed += 1
                    last_error = type(exc).__name__
                    logger.warning(
                        "[GatherX] File delivery failed user=%s file=%s error=%s",
                        user_id,
                        fpath,
                        exc,
                    )
                await asyncio.sleep(0.3)
        except Exception as exc:
            failed += max(1, len(files_to_send) - sent)
            last_error = type(exc).__name__
            logger.warning("[GatherX] Delivery failed user=%s error=%s", user_id, exc)
        finally:
            self._record_delivery_checkpoint(
                user_id,
                attempted=len(files_to_send),
                sent=sent,
                failed=failed,
                error=last_error,
            )
        return sent, failed

    async def deliver_updates(self):
        """Connect, deliver outputs, and disconnect while preserving partial progress."""
        try:
            await self.client.start(bot_token=self.token)  # type: ignore[attr-defined]
            await self.deliver_updates_active()
        except Exception as exc:
            logger.error("[GatherX] Delivery error: %s", exc)
        finally:
            try:
                await self.client.disconnect()  # type: ignore[attr-defined]
            except Exception as exc:
                logger.debug("[GatherX] Failed to disconnect bot client: %s", exc)
            await asyncio.sleep(0.25)

    async def deliver_updates_active(self):
        users = self._get_active_users()  # type: ignore[attr-defined]
        if not users:
            logger.info("[GatherX] No registered users — skipping delivery.")
            return

        files_to_send = self._collect_delivery_files(paths.OUTPUT_DIR)
        if not files_to_send:
            logger.info("[GatherX] No output files to deliver.")
            return

        logger.info(
            "[GatherX] Delivering %s file(s) to %s user(s)...",
            len(files_to_send),
            len(users),
        )
        delivered = 0
        failed = 0
        for user in users:
            sent, user_failed = await self._deliver_files_to_user(user, files_to_send)
            delivered += int(sent > 0)
            failed += int(user_failed > 0)
        logger.info("[GatherX] Delivery complete: %s users received data, %s had failures.", delivered, failed)

    def _collect_delivery_files(self, output_dir: Path, formats=None) -> List[tuple]:
        allowed = formats or _AUTO_DELIVER_FORMATS
        results: list[tuple] = []
        if not output_dir.exists():
            return results

        for f in sorted(output_dir.iterdir()):
            if not f.is_file() or f.stat().st_size == 0:
                continue
            name = f.name
            if not any(self._filename_matches_format(name, fmt) for fmt in allowed):
                continue

            size_kb = f.stat().st_size / 1024
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
        n = name.lower()
        f = fmt.lower()
        if f in ("npvt", "npvtsub"):
            return n.endswith(f".{f}") or n.endswith(f"_{f}.txt")
        if f in ("b64sub", "npvt.b64sub", "npvtsub.b64sub"):
            return ".b64sub" in n or n.endswith("_b64sub.txt")
        if f in ("decoded.json", "npvt.decoded.json", "npvtsub.decoded.json"):
            return ".decoded.json" in n or n.endswith("_decoded.json")
        return n.endswith(f".{f}") or n.endswith(f"_{f}.txt") or n.endswith(f"_{f}.json") or n.endswith(f"_{f}.zip")

    async def _send_format_to_user(self, chat_id: int, fmt: str):
        if fmt not in _ALL_VALID_FORMATS:
            await self._send_with_floodwait(
                self.client.send_message,  # type: ignore[attr-defined]
                chat_id,
                f"Unknown format `{fmt}`.\nUse /formats to see available formats.",
                parse_mode="md",
            )
            return

        sent = 0
        if paths.OUTPUT_DIR.exists():
            for f in sorted(paths.OUTPUT_DIR.iterdir()):
                if not f.is_file() or f.stat().st_size == 0:
                    continue
                if self._filename_matches_format(f.name, fmt):
                    size_kb = f.stat().st_size / 1024
                    label = _FORMAT_LABELS.get(fmt, fmt)
                    await self._send_with_floodwait(
                        self.client.send_file,  # type: ignore[attr-defined]
                        chat_id,
                        f,
                        caption=f"{label}\n`{f.name}` ({size_kb:.0f} KB)",
                        parse_mode="md",
                    )
                    sent += 1
                    await asyncio.sleep(0.3)

        if sent == 0:
            sent = await self._send_latest_to_user(chat_id, fmt=fmt, days=4)
        if sent == 0:
            await self._send_with_floodwait(
                self.client.send_message,  # type: ignore[attr-defined]
                chat_id,
                f"No files found for `{fmt}`.\nThe pipeline may not have produced this format yet.\nUse /formats to see all options.",
                parse_mode="md",
            )

    async def _send_latest_to_user(self, chat_id: int, fmt: Optional[str] = None, days: int = 4):
        files = self.artifact_store.list_archive(days=days)  # type: ignore[attr-defined]
        if not files:
            await self._send_with_floodwait(
                self.client.send_message,  # type: ignore[attr-defined]
                chat_id,
                f"No artifacts in the last {days} day(s).",
            )
            return 0

        sent = 0
        for f in files:
            if fmt and not self._filename_matches_format(f.name, fmt):
                continue
            size_kb = f.stat().st_size / 1024
            await self._send_with_floodwait(
                self.client.send_file,  # type: ignore[attr-defined]
                chat_id,
                f,
                caption=f"`{f.name}` ({size_kb:.0f} KB)",
                parse_mode="md",
            )
            sent += 1
            await asyncio.sleep(0.3)

        if sent == 0 and fmt:
            await self._send_with_floodwait(
                self.client.send_message,  # type: ignore[attr-defined]
                chat_id,
                f"No artifacts matching `{fmt}`.",
            )
        return sent
