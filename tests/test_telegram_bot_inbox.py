import asyncio
import hashlib

from huntx.connectors.telegram.connector import TelegramConnector
from huntx.state.db import DBConnection
from huntx.state.repo import StateRepo


def _update(update_id: int, chat_id: str = "-1001") -> dict:
    return {
        "update_id": update_id,
        "channel_post": {
            "message_id": update_id,
            "date": 2_000_000_000,
            "chat": {"id": chat_id},
            "text": f"payload-{update_id}",
        },
    }


async def _collect(connector: TelegramConnector, state=None):
    return [item async for item in connector._list_new_async(state)]


def test_bot_response_is_committed_before_confirming_poll(tmp_path):
    repo = StateRepo(DBConnection(tmp_path / "state.db"))
    connector = TelegramConnector("123:secret", "-1001", inbox=repo)
    events = []
    original_store = repo.store_bot_updates

    def recording_store(fingerprint, updates):
        events.append(("store", updates[0]["update_id"]))
        original_store(fingerprint, updates)

    async def request(_method, params):
        events.append(("poll", params["offset"]))
        if params["offset"] == 0:
            return {"ok": True, "result": [_update(41)]}
        return {"ok": True, "result": []}

    repo.store_bot_updates = recording_store
    connector._make_request_async = request

    items = asyncio.run(_collect(connector))

    assert [item.external_id for item in items] == ["41_text"]
    assert events == [("poll", 0), ("store", 41), ("poll", 42)]


def test_durable_inbox_survives_connector_restart(tmp_path):
    repo = StateRepo(DBConnection(tmp_path / "state.db"))
    first = TelegramConnector("123:secret", "-1001", inbox=repo)
    responses = iter(
        [
            {"ok": True, "result": [_update(51)]},
            {"ok": True, "result": []},
        ]
    )

    async def first_request(_method, _params):
        return next(responses)

    first._make_request_async = first_request
    asyncio.run(_collect(first))

    restarted = TelegramConnector("123:secret", "-1001", inbox=repo)

    async def empty_request(_method, params):
        assert params["offset"] == 52
        return {"ok": True, "result": []}

    restarted._make_request_async = empty_request
    items = asyncio.run(_collect(restarted, {"offset": 0}))

    assert [item.data for item in items] == [b"payload-51"]
    fingerprint = hashlib.sha256(b"123:secret").hexdigest()
    assert repo.get_bot_update_max_id(fingerprint) == 51


def test_durable_inbox_fans_out_one_token_to_multiple_chats(tmp_path):
    repo = StateRepo(DBConnection(tmp_path / "state.db"))
    fingerprint = hashlib.sha256(b"123:secret").hexdigest()
    repo.store_bot_updates(
        fingerprint,
        [_update(61, "-1001"), _update(62, "-1002")],
    )

    async def empty_request(_method, params):
        assert params["offset"] == 63
        return {"ok": True, "result": []}

    first = TelegramConnector("123:secret", "-1001", inbox=repo)
    second = TelegramConnector("123:secret", "-1002", inbox=repo)
    first._make_request_async = empty_request
    second._make_request_async = empty_request

    first_items = asyncio.run(_collect(first))
    second_items = asyncio.run(_collect(second))

    assert [item.external_id for item in first_items] == ["61_text"]
    assert [item.external_id for item in second_items] == ["62_text"]
