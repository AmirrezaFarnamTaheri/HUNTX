"""Bot startup must release its client even when initialization fails."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from huntx.bot.interactive import InteractiveBot


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["start", "handlers", "stats"])
async def test_startup_failure_disconnects_client(failure_stage):
    bot = object.__new__(InteractiveBot)
    bot.token = "123:fixture"
    bot.client = AsyncMock()
    bot._register_handlers = MagicMock()
    bot._get_user_count = MagicMock(return_value={"total": 0, "active": 0, "muted": 0})
    failure = RuntimeError("local startup failure")
    if failure_stage == "start":
        bot.client.start.side_effect = failure
    elif failure_stage == "handlers":
        bot._register_handlers.side_effect = failure
    else:
        bot._get_user_count.side_effect = failure

    with pytest.raises(RuntimeError, match="local startup failure"):
        await bot.start()

    bot.client.disconnect.assert_awaited_once()
    bot.client.run_until_disconnected.assert_not_awaited()


@pytest.mark.asyncio
async def test_normal_bot_shutdown_disconnects_once():
    bot = object.__new__(InteractiveBot)
    bot.token = "123:fixture"
    bot.client = AsyncMock()
    bot._register_handlers = MagicMock()
    bot._get_user_count = MagicMock(return_value={"total": 0, "active": 0, "muted": 0})

    await bot.start()

    bot.client.run_until_disconnected.assert_awaited_once()
    bot.client.disconnect.assert_awaited_once()
