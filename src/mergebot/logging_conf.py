import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

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
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(process)d | %(name)s:%(funcName)s:%(lineno)d - %(message)s'
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File Handler (optional)
    if log_file:
        try:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            # Fallback if file cannot be opened, log to console
            print(f"Failed to set up file logging at {log_file}: {e}", file=sys.stderr)

    # Adjust external libraries to reduce noise
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
