import logging
import os
import time
import urllib.error
import urllib.request
import urllib.parse
import json

import secrets

from ...utils.safe_names import safe_component

logger = logging.getLogger(__name__)

# Upper bound on how long a single API-supplied ``retry_after`` may park a
# publish worker. The value arrives in an untrusted JSON body, and publish runs
# on a bounded ThreadPoolExecutor whose futures the orchestrator can only
# *wait* on (never kill), so an unbounded sleep would wedge a worker for as
# long as the value says. Mirrors the HUNTX_FLOODWAIT_MAX_SECONDS pattern
# already used by bot/delivery.py.
_DEFAULT_MAX_RETRY_AFTER_SECONDS = 60


def _max_retry_after_seconds() -> int:
    raw = os.getenv("HUNTX_PUBLISH_MAX_RETRY_AFTER_SECONDS")
    if raw is None:
        return _DEFAULT_MAX_RETRY_AFTER_SECONDS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid HUNTX_PUBLISH_MAX_RETRY_AFTER_SECONDS=%r; using default %d",
            raw,
            _DEFAULT_MAX_RETRY_AFTER_SECONDS,
        )
        return _DEFAULT_MAX_RETRY_AFTER_SECONDS
    return value if value >= 0 else _DEFAULT_MAX_RETRY_AFTER_SECONDS


def _coerce_retry_after(raw: object) -> "int | None":
    """Coerce an API-supplied ``retry_after`` to a usable, bounded delay.

    Returns ``None`` when the value is absent, non-numeric (JSON may carry it
    as a string, which would make ``time.sleep`` raise ``TypeError``), not
    positive, or larger than the configured ceiling — in which case the caller
    must not sleep and should surface the error instead.
    """
    # bool is an int subclass; True must not become a 1-second sleep. Narrow to
    # the types int() actually accepts here so the conversion is type-safe
    # rather than relying on catching TypeError from an arbitrary object.
    if raw is None or isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        if raw is not None:
            logger.warning("Ignoring non-numeric retry_after from Telegram API: %r", raw)
        return None
    try:
        delay = int(raw)
    except (TypeError, ValueError):
        logger.warning("Ignoring non-numeric retry_after from Telegram API: %r", raw)
        return None
    if delay <= 0:
        return None
    ceiling = _max_retry_after_seconds()
    if delay > ceiling:
        logger.warning(
            "Telegram API requested retry_after=%ss which exceeds the %ss ceiling; "
            "not sleeping (raise HUNTX_PUBLISH_MAX_RETRY_AFTER_SECONDS to allow longer waits)",
            delay,
            ceiling,
        )
        return None
    return delay


def _safe_multipart_filename(filename: str) -> str:
    """Return a filename safe to embed in a Content-Disposition header.

    The filename lands inside a quoted-string, so a raw ``"`` or ``\\`` would
    terminate/escape the parameter and a CR/LF would terminate the header
    entirely — letting a crafted name smuggle extra multipart parts or corrupt
    the request. ``safe_component`` collapses everything outside
    ``[A-Za-z0-9._-]`` to ``_``, which removes all of those characters by
    construction (and is idempotent for the names this pipeline generates).
    """
    return safe_component(filename, default="artifact.bin", max_len=200)


class TelegramPublisher:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"

        # Validation. Deliberately does not echo any part of the token — even a
        # prefix is credential material and this line would land in shared logs.
        if not self.token or ":" not in self.token:
            logger.warning(
                "Initialized TelegramPublisher with a malformed bot token "
                "(expected the '<id>:<secret>' form); publishing will fail."
            )

    def publish(self, chat_id: str, data: bytes, filename: str, caption: str = ""):
        # Using multipart/form-data is complex with urllib standard lib.
        # But we must do it to send files.
        # To avoid dependencies like 'requests', we implement a simple multipart encoder.

        boundary = f"----HuntXBoundary{secrets.token_hex(8)}"
        lines = []

        # Chat ID
        lines.append(f"--{boundary}")
        lines.append('Content-Disposition: form-data; name="chat_id"')
        lines.append("")
        lines.append(chat_id)

        # Caption
        if caption:
            lines.append(f"--{boundary}")
            lines.append('Content-Disposition: form-data; name="caption"')
            lines.append("")
            lines.append(caption)

        # File
        safe_filename = _safe_multipart_filename(filename)
        lines.append(f"--{boundary}")
        lines.append(f'Content-Disposition: form-data; name="document"; filename="{safe_filename}"')
        lines.append("Content-Type: application/octet-stream")
        lines.append("")

        # Construct body
        body_start = "\r\n".join(lines).encode("utf-8") + b"\r\n"
        body_end = f"\r\n--{boundary}--\r\n".encode("utf-8")

        body = body_start + data + body_end

        payload_size = len(body)
        payload_size_kb = payload_size / 1024

        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(payload_size)}

        # Never log the full URL here (it contains the bot token).
        logger.debug(f"Sending document to chat_id={chat_id}. Payload size: {payload_size_kb:.2f} KB.")

        req = urllib.request.Request(f"{self.base_url}/sendDocument", data=body, headers=headers)

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    resp_code = response.getcode()
                    resp_body = response.read().decode("utf-8")
                    logger.debug(f"Telegram API Response Code: {resp_code}")

                    payload = json.loads(resp_body)
                    if not payload.get("ok"):
                        error_msg = payload.get("description", "Unknown Telegram error")
                        params = payload.get("parameters", {})
                        retry_after = _coerce_retry_after(params.get("retry_after"))
                        if retry_after is not None and attempt < max_attempts:
                            logger.warning(f"Telegram API rate limited (attempt {attempt}/{max_attempts}). Sleeping for {retry_after}s: {error_msg}")
                            time.sleep(retry_after)
                            continue
                        raise RuntimeError(f"Telegram API error: {error_msg}")

                    return payload
            except urllib.error.HTTPError as e:
                try:
                    resp_body = e.read().decode("utf-8")
                    payload = json.loads(resp_body)
                    error_msg = payload.get("description", str(e))

                    if e.code == 429 and attempt < max_attempts:
                        params = payload.get("parameters", {})
                        retry_after = _coerce_retry_after(params.get("retry_after"))
                        if retry_after is None:
                            retry_after = 5  # sane default when absent/invalid/over-ceiling
                        logger.warning(f"Telegram API rate limited with HTTP 429 (attempt {attempt}/{max_attempts}). Sleeping for {retry_after}s: {error_msg}")
                        time.sleep(retry_after)
                        continue

                    logger.error(f"Telegram API HTTP error {e.code}: {error_msg}")
                    raise RuntimeError(f"Telegram API HTTP {e.code}: {error_msg}")
                except RuntimeError:
                    raise
                except Exception as ex:
                    logger.error(f"Telegram API HTTP error {e.code}: {ex}")
                    raise
            except Exception as e:
                logger.error(f"Telegram publish failed for {chat_id} (attempt {attempt}/{max_attempts}): {e}")
                if attempt < max_attempts:
                    time.sleep(2 * attempt)
                    continue
                raise
