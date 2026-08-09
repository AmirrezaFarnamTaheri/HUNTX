from unittest.mock import Mock

from huntx.connectors.telegram.hardening import install_telegram_connector_hardening


class DummyConnector:
    def __init__(self, token, chat_id, state=None, fetch_windows=None, inbox=None):
        self.token = token
        self.target_chat_id = str(chat_id)
        self.offset = 10
        self._inbox = inbox
        self._token_fingerprint = "a" * 64

    async def _list_new_async(self, state=None):
        yield Mock(external_id="one", metadata={"update_id": 11})
        yield Mock(external_id="two", metadata={"update_id": 11})

    async def _make_request_async(self, method, params=None):
        return {"ok": True}

    async def _download_file_async(self, path):
        return b"ok"

    def get_state(self):
        return {"offset": self.offset}


def test_partial_ack_keeps_update_replayable():
    install_telegram_connector_hardening(DummyConnector)
    connector = DummyConnector("token", "chat")

    import asyncio

    async def run():
        items = []
        async for item in connector._list_new_async({"offset": 10}):
            items.append(item)
        connector.acknowledge(items[:1])
        assert connector.get_state()["offset"] == 10

    asyncio.run(run())
