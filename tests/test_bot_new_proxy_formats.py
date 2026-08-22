from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from huntx.bot.handlers import HandlersMixin


class _Bot(HandlersMixin):
    def __init__(self) -> None:
        self.client = AsyncMock()


@pytest.mark.asyncio
async def test_public_formats_response_lists_client_derivatives():
    bot = _Bot()

    await bot._respond_formats(123)

    text = bot.client.send_message.await_args.args[1]
    for fmt in ("raw.txt", "singbox.json", "xray.json", "nekobox.json"):
        assert f"`{fmt}`" in text
