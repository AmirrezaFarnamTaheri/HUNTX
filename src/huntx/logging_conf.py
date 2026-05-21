import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional


class _RedactSecretsFilter(logging.Filter):
    """
    Best-effort log redaction filter to prevent accidental secret leaks in logs.
    """

    _bot_token_in_url = re.compile(r"(https?://api\.telegram\.org/(file/)?bot)(\d+):([^/\s]+)", re.IGNORECASE)
    _bot_token_generic = re.compile(r"\b(bot)?(\d+):([A-Za-z0-9_-]{30,})\b")
    _kv_secrets = re.compile(
        r"\b(TELEGRAM_TOKEN|PUBLISH_BOT_TOKEN|AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID|TELEGRAM_API_HASH|TELEGRAM_USER_SESSION|AWS_SESSION_TOKEN)\s*[:=]\s*([^\s]+)\b",
        re.IGNORECASE
    )

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True

        redacted = msg
        redacted = self._bot_token_in_url.sub(r"\1\3:***REDACTED***", redacted)
        redacted = self._bot_token_generic.sub(r"***REDACTED***", redacted)
        redacted = self._kv_secrets.sub(r"\1=***REDACTED***", redacted)

        if redacted != msg:
            # Override message and clear args to prevent re-formatting of secrets.
            record.msg = redacted
            record.args = ()

        return True


def setup_logging(log_level: int = logging.INFO, log_file: Optional[str] = None):
    """
    Configures logging for the application.

    Args:
        log_level: The logging level (e.g., logging.INFO, logging.DEBUG).
        log_file: Optional path to a file where logs should be written.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to prevent duplication
    if root_logger.handlers:
        root_logger.handlers = []

    # Detailed formatter
    # Including threadName, module, pathname for maximum context
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(module)s:%(funcName)s:%(lineno)d - %(message)s"
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(_RedactSecretsFilter())
    root_logger.addHandler(console_handler)

    # File Handler (optional)
    if log_file:
        try:
            file_handler = RotatingFileHandler(
                log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"  # 10 MB
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(_RedactSecretsFilter())
            root_logger.addHandler(file_handler)
        except Exception as e:
            # Fallback if file cannot be opened, log to console
            print(f"Failed to set up file logging at {log_file}: {e}", file=sys.stderr)

    # Adjust external libraries to reduce noise
    # We keep these at WARNING unless the root level is specifically DEBUG,
    # in which case we might want to see them?
    # For now, keeping them quiet is safer for readability of app logs.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
