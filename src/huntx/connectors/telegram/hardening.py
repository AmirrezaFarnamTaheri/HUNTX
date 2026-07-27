"""Durable acknowledgement fencing for the Telegram Bot API connector."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Iterable, Optional, Set, Tuple, Type

ItemKey = Tuple[int, str]


def install_telegram_connector_hardening(connector_type: Type[Any]) -> None:
    if getattr(connector_type, "_huntx_ack_hardening_installed", False):
        return

    original_init = connector_type.__init__
    original_list_new_async = connector_type._list_new_async
    original_make_request_async = connector_type._make_request_async
    original_download_file_async = connector_type._download_file_async
    original_get_state = connector_type.get_state

    def hardened_init(
        self: Any,
        token: str,
        chat_id: str,
        state: Optional[Dict[str, Any]] = None,
        fetch_windows: Optional[Dict[str, Any]] = None,
        inbox: Optional[Any] = None,
    ) -> None:
        original_init(self, token, chat_id, state, fetch_windows, inbox)
        self._consumer_id = f"chat:{self.target_chat_id}"
        self._scan_start_offset = int(self.offset)
        self._scan_completed = False
        self._scan_failed = False
        self._last_yielded_update_id: Optional[int] = None
        self._yielded_item_keys: Set[ItemKey] = set()
        self._acknowledged_item_keys: Set[ItemKey] = set()
        self._pending_ack_update_id = int(self.offset)

    async def hardened_make_request_async(
        self: Any,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        response = await original_make_request_async(self, method, params)
        if not response.get("ok"):
            self._scan_failed = True
        return response

    async def hardened_download_file_async(self: Any, file_path: str) -> Optional[bytes]:
        data = await original_download_file_async(self, file_path)
        if data is None:
            self._scan_failed = True
        return data

    async def hardened_list_new_async(
        self: Any,
        state: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Any]:
        local_offset = int(state.get("offset", 0)) if state else 0
        self._scan_start_offset = local_offset
        self._scan_completed = False
        self._scan_failed = False
        self._last_yielded_update_id = None
        self._yielded_item_keys.clear()
        self._acknowledged_item_keys.clear()
        self._pending_ack_update_id = local_offset

        if self._inbox is not None and hasattr(self._inbox, "register_bot_consumer"):
            self._inbox.register_bot_consumer(
                self._token_fingerprint,
                self._consumer_id,
                local_offset,
            )

        completed = False
        try:
            async for item in original_list_new_async(self, state):
                update_id = int(item.metadata.get("update_id", 0))
                if update_id > 0:
                    key = (update_id, str(item.external_id))
                    self._yielded_item_keys.add(key)
                    self._last_yielded_update_id = update_id
                yield item
            completed = True
        finally:
            self._scan_completed = completed

    def acknowledge(self: Any, items: Iterable[Any]) -> None:
        for item in items:
            update_id = int(item.metadata.get("update_id", 0))
            if update_id > 0:
                self._acknowledged_item_keys.add((update_id, str(item.external_id)))

        unacknowledged = self._yielded_item_keys - self._acknowledged_item_keys
        if unacknowledged:
            candidate = min(update_id for update_id, _ in unacknowledged) - 1
        elif self._scan_completed and not self._scan_failed:
            candidate = int(self.offset)
        elif self._last_yielded_update_id is not None:
            candidate = self._last_yielded_update_id - 1
        else:
            candidate = self._scan_start_offset

        self._pending_ack_update_id = max(
            self._scan_start_offset,
            min(int(self.offset), int(candidate)),
        )

    def hardened_get_state(self: Any) -> Dict[str, Any]:
        state = dict(original_get_state(self))
        state["offset"] = int(self._pending_ack_update_id)
        return state

    def commit_acknowledgement(self: Any) -> None:
        if self._inbox is None or not hasattr(self._inbox, "acknowledge_bot_consumer"):
            return
        self._inbox.acknowledge_bot_consumer(
            self._token_fingerprint,
            self._consumer_id,
            int(self._pending_ack_update_id),
        )

    connector_type.__init__ = hardened_init
    connector_type._make_request_async = hardened_make_request_async
    connector_type._download_file_async = hardened_download_file_async
    connector_type._list_new_async = hardened_list_new_async
    connector_type.acknowledge = acknowledge
    connector_type.get_state = hardened_get_state
    connector_type.commit_acknowledgement = commit_acknowledgement
    connector_type._huntx_ack_hardening_installed = True
