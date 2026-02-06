import logging
from typing import Dict, Optional, Type
from .base import FormatHandler

logger = logging.getLogger(__name__)

class FormatRegistry:
    _instance = None
    _handlers: Dict[str, FormatHandler] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FormatRegistry, cls).__new__(cls)
            cls._handlers = {}
        return cls._instance

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, handler: FormatHandler):
        if handler.format_id in self._handlers:
            logger.warning(f"Overwriting handler for format: {handler.format_id}")
        else:
            logger.debug(f"Registered format handler: {handler.format_id}")
        self._handlers[handler.format_id] = handler

    def get(self, format_id: str) -> Optional[FormatHandler]:
        handler = self._handlers.get(format_id)
        if not handler:
            logger.warning(f"Requested unknown format: {format_id}")
            return None
        return handler

    def list_formats(self):
        return list(self._handlers.keys())
