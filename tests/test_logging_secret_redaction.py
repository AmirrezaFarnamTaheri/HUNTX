from __future__ import annotations

import io
import logging

from huntx.logging_conf import _RedactingFormatter, _RedactSecretsFilter


def _render_exception(message: str) -> str:
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.addFilter(_RedactSecretsFilter())
    handler.setFormatter(_RedactingFormatter("%(message)s"))

    logger = logging.getLogger("huntx-test-secret-redaction")
    old_handlers = list(logger.handlers)
    old_propagate = logger.propagate
    old_level = logger.level
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        try:
            raise RuntimeError(message)
        except RuntimeError:
            logger.exception("request failed")
        return buffer.getvalue()
    finally:
        logger.handlers = old_handlers
        logger.propagate = old_propagate
        logger.setLevel(old_level)


def test_exception_traceback_redacts_telegram_bot_token():
    secret = "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
    rendered = _render_exception(
        f"failed https://api.telegram.org/bot{secret}/getMe"
    )

    assert secret not in rendered
    assert "***REDACTED***" in rendered
    assert "RuntimeError" in rendered


def test_exception_traceback_redacts_named_secret_value():
    secret = "super-secret-session-value"
    rendered = _render_exception(f"TELEGRAM_USER_SESSION={secret}")

    assert secret not in rendered
    assert "TELEGRAM_USER_SESSION=***REDACTED***" in rendered
