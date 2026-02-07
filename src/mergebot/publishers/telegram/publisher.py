import logging
import urllib.request
import urllib.parse
import json

logger = logging.getLogger(__name__)

class TelegramPublisher:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"

        # Validation
        if not self.token or ':' not in self.token:
             logger.warning(f"Initialized TelegramPublisher with potentially invalid token: {self.token[:5]}... (missing colon)")

    def publish(self, chat_id: str, data: bytes, filename: str, caption: str = ""):
        # Using multipart/form-data is complex with urllib standard lib.
        # But we must do it to send files.
        # To avoid dependencies like 'requests', we implement a simple multipart encoder or use boundaries.

        boundary = '----WebKitFormBoundaryMergeBot7MA4YWxkTrZu0gW'
        lines = []

        # Chat ID
        lines.append(f'--{boundary}')
        lines.append('Content-Disposition: form-data; name="chat_id"')
        lines.append('')
        lines.append(chat_id)

        # Caption
        if caption:
            lines.append(f'--{boundary}')
            lines.append('Content-Disposition: form-data; name="caption"')
            lines.append('')
            lines.append(caption)

        # File
        lines.append(f'--{boundary}')
        lines.append(f'Content-Disposition: form-data; name="document"; filename="{filename}"')
        lines.append('Content-Type: application/octet-stream')
        lines.append('')

        # Construct body
        body_start = "\r\n".join(lines).encode("utf-8") + b"\r\n"
        body_end = f"\r\n--{boundary}--\r\n".encode("utf-8")

        body = body_start + data + body_end

        payload_size = len(body)
        payload_size_kb = payload_size / 1024

        headers = {
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Content-Length': str(payload_size)
        }

        logger.debug(f"Sending document to {chat_id}. Payload size: {payload_size_kb:.2f} KB. URL: {self.base_url}/sendDocument")

        req = urllib.request.Request(f"{self.base_url}/sendDocument", data=body, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                resp_code = response.getcode()
                resp_body = response.read().decode("utf-8")
                logger.info(f"Telegram API Response Code: {resp_code}")
                return json.loads(resp_body)
        except Exception as e:
            logger.error(f"Telegram publish failed for {chat_id}: {e}")
            raise
