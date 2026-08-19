import logging
from typing import Dict, Optional

from .base import FormatHandler

logger = logging.getLogger(__name__)


class FormatRegistry:
    """Registry for parser/build handlers with explicit output capability checks."""

    _shared_instance = None
    _PARSE_ONLY_FORMATS = frozenset({"nm", "slipnet"})

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
            logger.warning("Overwriting handler for format: %s", handler.format_id)
        else:
            logger.debug("Registered format handler: %s", handler.format_id)
        self._handlers[handler.format_id] = handler

    def get(self, format_id: str) -> Optional[FormatHandler]:
        handler = self._handlers.get(format_id)
        if not handler:
            logger.warning("Requested unknown format: %s", format_id)
            return None
        return handler

    def list_formats(self):
        return list(self._handlers.keys())

    def can_build(self, format_id: str) -> bool:
        """Return whether a registered format supports direct artifact building.

        ``nm`` and ``slipnet`` currently implement parsing only; their concrete
        ``build`` methods raise ``NotImplementedError``. Keeping that capability
        explicit prevents validation from accepting a route that can only fail
        later at build time while preserving the existing registry API.
        """
        return format_id in self._handlers and format_id not in self._PARSE_ONLY_FORMATS
