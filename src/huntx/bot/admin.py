import asyncio
import logging
import os
from telethon import Button
from typing import Optional
from ..store import paths

logger = logging.getLogger(__name__)


class AdminMixin:
    # These methods are designed to be mixed into InteractiveBot.

    def _is_admin(self, user_id: str, username: Optional[str] = None) -> bool:
        admins_str = os.environ.get("HUNTX_ADMINS", "")
        if not admins_str