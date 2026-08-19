import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from huntx.bot.delivery import DeliveryMixin, FloodWaitError
from huntx.state.db import open_db


class _Harness(DeliveryMixin):
    pass


def _flood_wait(seconds: int):
    try:
        exc = FloodWaitError(request=None, capture=seconds)
    except TypeError:
        exc = FloodWaitError()
    exc.seconds = seconds
    return exc


def _harness(tmp_path):
    harness = _Harness()
    harness.db = open_db(tmp_path / "state.db")
    harness.client = SimpleNamespace(
        send_message=AsyncMock(),
        send_file=AsyncMock(),
    )
    harness._is_admin = MagicMock(return_value=False)
    return harness


def test_delivery_layer_requires_approved_private_identity(tmp_path):
    harness = _harness(tmp_path)
    with harness.db.connect() as conn:
        conn.execute(
            """
            INSERT INTO bot_users (user_id, chat_id, registered_at, approved, muted)
            VALUES ('1', '1', 0, 1, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO bot_users (user_id, chat_id, registered_at, approved, muted)
            VALUES ('2', '-10099', 0, 1, 0)
            """
        )
        conn.execute(
            """
            INSERT INTO bot_users (user_id, chat_id, registered_at, approved, muted)
            VALUES ('3', '3', 0, 0, 0)
            """
        )

    assert harness._artifact_chat_authorized(1) is True
    assert harness._artifact_chat_authorized(-10099) is False
    assert harness._artifact_chat_authorized(3) is False
    assert harness._artifact_chat_authorized(999) is False


def test_direct_send_to_unauthorized_chat_is_blocked(tmp_path):
    harness = _harness(tmp_path)

    asyncio.run(harness._send_format_to_user(9, "npvt"))

    harness.client.send_file.assert_not_awaited()
    harness.client.send_message.assert_awaited_once()
    assert "requires an approved private" in harness.client.send_message.await_args.args[1]


def test_malformed_floodwait_env_uses_safe_defaults(tmp_path):
    harness = _harness(tmp_path)
    calls = 0

    async def method():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _flood_wait(1)
        return "ok"

    with (
        patch.dict(
            os.environ,
            {
                "HUNTX_FLOODWAIT_MAX_SECONDS": "not-an-int",
                "HUNTX_FLOODWAIT_MAX_RETRIES": "also-bad",
            },
            clear=False,
        ),
        patch("huntx.bot.delivery.asyncio.sleep", new=AsyncMock()),
    ):
        assert asyncio.run(harness._send_with_floodwait(method)) == "ok"

    assert calls == 2
