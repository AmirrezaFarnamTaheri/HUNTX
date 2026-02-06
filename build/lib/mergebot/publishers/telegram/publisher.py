import logging
import urllib.request
import urllib.parse
import json

logger = logging.getLogger(__name__)

class TelegramPublisher:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"

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

        headers = {
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Content-Length': str(len(body))
        }

        req = urllib.request.Request(f"{self.base_url}/sendDocument", data=body, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Telegram publish failed: {e}")
            raise
