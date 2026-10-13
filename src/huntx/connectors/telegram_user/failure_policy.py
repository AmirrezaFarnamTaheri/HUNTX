from __future__ import annotations

from typing import Optional


_PERMANENT_PEER_ERROR_NAMES = frozenset(
    {
        "ChannelInvalidError",
        "ChannelPrivateError",
        "ChatIdInvalidError",
        "PeerIdInvalidError",
        "UsernameInvalidError",
        "UsernameNotOccupiedError",
    }
)

_PERMANENT_VALUE_ERROR_MARKERS = (
    "no user has ",
    "could not find the input entity for",
    "cannot find any entity corresponding to",
    "username is not in use",
)


def telegram_flood_wait_seconds(exc: BaseException) -> int | None:
    """Extract Telegram's explicit Retry-After without parsing arbitrary error strings.

    Telethon's FloodWaitError exposes `seconds`; a wrapped exception may keep
    it as its cause or context. Never silently shorten the server's cooldown,
    mistake a generic timeout for a flood wait, or quarantine the source.
    """
    current: Optional[BaseException] = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if type(current).__name__ in {"FloodWaitError", "FloodPremiumWaitError"}:
            seconds = getattr(current, "seconds", None)
            if type(seconds) is int and 0 < seconds <= 30 * 24 * 3600:
                return seconds
        current = current.__cause__ or current.__context__
    return None


def is_permanent_telegram_peer_error(exc: BaseException) -> bool:
    """Return whether retrying the configured Telegram peer cannot self-heal.

    Transport failures, timeouts, flood waits, and other operational errors are
    deliberately excluded so the normal retry/backoff path remains intact.
    """
    current: Optional[BaseException] = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if type(current).__name__ in _PERMANENT_PEER_ERROR_NAMES:
            return True
        if isinstance(current, ValueError):
            message = str(current).casefold()
            if any(marker in message for marker in _PERMANENT_VALUE_ERROR_MARKERS):
                return True
        current = current.__cause__ or current.__context__
    return False
