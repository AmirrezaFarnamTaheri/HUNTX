import asyncio
import inspect
from typing import Protocol, Dict, Any, Optional, AsyncIterator, Union, Iterator


async def maybe_await(val):
    """
    Transparently await a value if it's awaitable (like a coroutine or future),
    otherwise return the value directly. Useful for unit tests where MagicMock is injected.
    """
    if val is not None and inspect.isawaitable(val):
        return await val
    return val



class AsyncSyncIterator:
    """
    Helper wrapper that implements both __iter__ (sync) and __aiter__ (async).
    Allows connector methods to yield values asynchronously while maintaining
    full compatibility with synchronous iteration (like in existing unit tests).
    """
    def __init__(self, async_gen):
        self.async_gen = async_gen

    def __aiter__(self):
        return self.async_gen

    def __iter__(self):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def collect():
            items = []
            async for item in self.async_gen:
                items.append(item)
            return items

        return iter(loop.run_until_complete(collect()))


async def async_iter(iterable):
    """
    Asynchronously iterates over any iterable, supporting both async iterators
    (which have __aiter__) and synchronous iterables (like lists or sync generators).
    """
    if hasattr(iterable, "__aiter__"):
        async for item in iterable:
            yield item
    else:
        for item in iterable:
            yield item


class SourceItem(Protocol):
    external_id: str
    data: bytes
    metadata: Dict[str, Any]  # must contain 'filename' if possible


class SourceConnector(Protocol):
    deadline: Optional[float] = None

    def list_new(self, state: Optional[Dict[str, Any]]) -> Union[AsyncIterator[SourceItem], Iterator[SourceItem]]:
        """
        Yields new items since the last state.
        Can be an async iterator or a synchronous iterator wrapped in AsyncSyncIterator.
        """
        ...

    def get_state(self) -> Dict[str, Any]:
        """Return current state (e.g. last_offset) to be saved."""
        ...
