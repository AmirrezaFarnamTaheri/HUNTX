import logging
from typing import Dict, Optional
from .base import FormatHandler

logger = logging.getLogger(__name__)


class FormatRegistry:
    _shared_instance = None

    def __init__(self):
        self._handlers: Dict[str, FormatHandler] = {}

    @classmethod
    def get_instance(cls):
        """Return the compatibility registry used by config validation.

        Runtime owners should construct ``FormatRegistry()`` directly so one
        orchestrator cannot overwrite another orchestrator's handlers.
        """
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

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
