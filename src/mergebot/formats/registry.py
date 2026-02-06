from typing import Dict, Type
from .base import FormatHandler

class FormatRegistry:
    _instance = None
    _handlers: Dict[str, FormatHandler] = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, handler: FormatHandler):
        self._handlers[handler.format_id] = handler

    def get(self, format_id: str) -> FormatHandler:
        if format_id not in self._handlers:
            raise ValueError(f"Unknown format: {format_id}")
        return self._handlers[format_id]

    def list_formats(self):
        return list(self._handlers.keys())
