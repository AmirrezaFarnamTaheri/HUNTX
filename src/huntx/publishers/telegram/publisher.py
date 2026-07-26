import logging
import urllib.request
import urllib.parse
import json

import secrets

logger = logging.getLogger(__name__)


class TelegramPublisher:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"

        # Validation
        if not self.token or ":" not in self.token:
            logger.warning(
                f"Initialized TelegramPublisher with potentially invalid token: {self.token[:5]}... (missing colon)"
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
        lines.append(f"--{boundary}")
        lines.append(f'Content-Disposition: form-data; name="document"; filename="{filename}"')
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
                        retry_after = params.get("retry_after")
                        if retry_after and attempt < max_attempts:
                            import time
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
                        retry_after = params.get("retry_after") or 5
                        import time
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
                    import time
                    time.sleep(2 * attempt)
                    continue
                raise
