import logging
import time
import urllib.request
import urllib.error
import json
import hashlib
from dataclasses import dataclass
from typing import Dict, Any, Optional
from ..base import SourceConnector, AsyncSyncIterator


@dataclass
class TelegramItem:
    """Concrete SourceItem for Bot API connector."""

    __slots__ = ("external_id", "data