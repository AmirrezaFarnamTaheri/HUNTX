"""Telegram Bot API connector package."""

from .connector import TelegramConnector, TelegramItem
from .hardening import install_telegram_connector_hardening

install_telegram_connector_hardening(TelegramConnector)

__all__ = ["TelegramConnector", "TelegramItem"]
