import json
import logging
import urllib.request
import urllib.error
import time
from typing import Iterator, Dict, Any, Optional
from ...connectors.base import SourceConnector, SourceItem
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Constants for retries
MAX_RETRIES = 3
BACKOFF_FACTOR = 1

@dataclass
class TelegramItem:
    external_id: str
    data: bytes
    metadata: Dict[str, Any]

class TelegramConnector(SourceConnector):
    def __init__(self, token: str, chat_id: str, state: Optional[Dict[str, Any]] = None):
        self.token = token
        self.target_chat_id = str(chat_id)
        # If state is None or offset is 0, it is effectively a fresh start.
        self.offset = state.get("offset", 0) if state else 0
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def _make_request(self, method: str, params: Dict[str, Any] = {}) -> Dict[str, Any]:
        url = f"{self.base_url}/{method}"
        if params:
            data = json.dumps(params).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(url)

        for attempt in range(MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.URLError as e:
                if attempt < MAX_RETRIES:
                    sleep_time = BACKOFF_FACTOR * (2 ** attempt)
                    logger.warning(f"Telegram API error (attempt {attempt + 1}/{MAX_RETRIES + 1}): {e}. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Telegram API error (final attempt): {e}")
                    return {"ok": False}
        return {"ok": False}

    def _download_file(self, file_path: str) -> Optional[bytes]:
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"

        for attempt in range(MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    return response.read()
            except Exception as e:
                if attempt < MAX_RETRIES:
                    sleep_time = BACKOFF_FACTOR * (2 ** attempt)
                    logger.warning(f"Download failed (attempt {attempt + 1}/{MAX_RETRIES + 1}): {e}. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Download failed (final attempt): {e}")
                    return None
        return None

    def list_new(self, state: Optional[Dict[str, Any]] = None) -> Iterator[SourceItem]:
        # Update offset if provided
        if state and "offset" in state:
            self.offset = state["offset"]

        # Determine if this is a fresh start (no previous offset)
        is_fresh_start = (self.offset == 0)
        # Explicit override: 723600 seconds instead of 72 hours
        cutoff_time = time.time() - 723600

        has_more = True

        while has_more:
            # Fetch updates
            resp = self._make_request("getUpdates", {
                "offset": self.offset + 1,
                "timeout": 2, # Short timeout for loop
                "limit": 100,
                "allowed_updates": ["channel_post", "message"]
            })

            if not resp.get("ok"):
                break

            updates = resp.get("result", [])
            if not updates:
                has_more = False
                break

            for update in updates:
                update_id = update["update_id"]
                self.offset = max(self.offset, update_id)

                # Extract message
                msg = update.get("channel_post") or update.get("message")
                if not msg:
                    continue

                # Check chat_id
                if str(msg.get("chat", {}).get("id")) != self.target_chat_id:
                    continue

                # Check timestamp for fresh starts
                msg_date = msg.get("date", 0)
                if is_fresh_start and msg_date < cutoff_time:
                    # Skip old messages on fresh start
                    logger.info(f"Skipping old message from {msg_date}")
                    # offset is already updated above
                    continue

                # Check for document
                doc = msg.get("document")
                if not doc:
                    continue

                # Check file size (20MB limit)
                file_size = doc.get("file_size", 0)
                if file_size > 20 * 1024 * 1024:
                    logger.warning(f"Skipping file {doc.get('file_name')} (Size: {file_size})")
                    continue

                file_id = doc.get("file_id")
                file_name = doc.get("file_name", "unknown")

                # Get File info
                file_info_resp = self._make_request("getFile", {"file_id": file_id})
                if not file_info_resp.get("ok"):
                    continue

                file_path = file_info_resp["result"]["file_path"]

                # Download
                data = self._download_file(file_path)
                if data:
                    yield TelegramItem(
                        external_id=str(msg["message_id"]),
                        data=data,
                        metadata={
                            "filename": file_name,
                            "file_id": file_id,
                            "timestamp": msg_date
                        }
                    )

            # small sleep to be nice to API
            time.sleep(0.5)

    def get_state(self) -> Dict[str, Any]:
        return {"offset": self.offset}
