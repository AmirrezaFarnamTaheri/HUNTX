from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

_BOT_TOKEN_IN_URL = re.compile(
    r"(https?://api\.telegram\.org/(file/)?bot)(\d+):([^/\s]+)",
    re.IGNORECASE,
)
_BOT_TOKEN_GENERIC = re.compile(r"\b(bot)?(\d+):([A-Za-z0-9_-]{30,})\b")
_KV_SECRETS = re.compile(
    r"\b(TELEGRAM_TOKEN|PUBLISH_BOT_TOKEN|AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID|"
    r"TELEGRAM_API_HASH|TELEGRAM_USER_SESSION|AWS_SESSION_TOKEN)\s*[:=]\s*([^\s]+)\b",
    re.IGNORECASE,
)


def _redact_secret_text(value: str) -> str:
    """Redact known credential shapes from an already-rendered log string."""
    redacted = _BOT_TOKEN_IN_URL.sub(r"\1\3:***REDACTED***", value)
    redacted = _BOT_TOKEN_GENERIC.sub(r"***REDACTED***", redacted)
    return _KV_SECRETS.sub(r"\1=***REDACTED***", redacted)


class _RedactSecretsFilter(logging.Filter):
    """Redact ordinary message arguments before they reach any formatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = _redact_secret_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class _RedactingFormatter(logging.Formatter):
    """Redact the final formatted record, including exception/stack text.

    Logging filters run before ``Formatter.format`` appends ``exc_info`` and
    ``stack_info``. Redacting the final string closes that gap so a token
    carried by an exception message cannot bypass the ordinary record filter.
    """

    def format(self, record: logging.LogRecord) -> str:
        return _redact_secret_text(super().format(record))


def setup_logging(log_level: int = logging.INFO, log_file: Optional[str] = None):
    """Configure root logging with bounded files and end-to-end redaction."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to prevent duplication.
    if root_logger.handlers:
        root_logger.handlers = []

    formatter = _RedactingFormatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | "
        "%(module)s:%(funcName)s:%(lineno)d - %(message)s"
    )
    redaction_filter = _RedactSecretsFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redaction_filter)
    root_logger.addHandler(console_handler)

    if log_file:
        try:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(_RedactSecretsFilter())
            root_logger.addHandler(file_handler)
        except Exception as exc:
            # Avoid interpolating caller-controlled log path details into the
            # root logger while it is being configured. stderr is the only
            # reliable fallback at this point.
            print(
                f"Failed to set up file logging: {type(exc).__name__}",
                file=sys.stderr,
            )

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
