from __future__ import annotations

from huntx.bot.interactive import InteractiveBot
from huntx.state.db import open_db


def test_new_bot_users_are_denied_auto_delivery_until_approved(tmp_path):
    bot = object.__new__(InteractiveBot)
    bot.db = open_db(tmp_path / "state.db")
    bot._init_tables()

    assert bot._register_user("12345", "12345", "new") is True
    assert bot._get_active_users() == []

    with bot.db.connect() as conn:
        conn.execute(
            "UPDATE bot_users SET approved = 1 WHERE user_id = ?",
            ("12345",),
        )

    assert [(row["user_id"], row["chat_id"]) for row in bot._get_active_users()] == [
        ("12345", "12345")
    ]


def test_non_private_chat_cannot_become_delivery_target(tmp_path):
    bot = object.__new__(InteractiveBot)
    bot.db = open_db(tmp_path / "state.db")
    bot._init_tables()

    assert bot._register_user("12345", "-100987654", "group-user") is False
    assert bot._get_user_info("12345") is None
