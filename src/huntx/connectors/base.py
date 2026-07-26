import asyncio
import concurrent.futures
import inspect
from typing import Protocol, Dict, Any, Optional, AsyncIterator, Union, Iterator, TypeVar, Coroutine

_T = TypeVar("_T")


async def maybe_await(val):
    """
    Transparently await a value if it's awaitable (like a coroutine or future),
    otherwise return the value directly. Useful for unit tests where MagicMock is injected.
    """
    if val is not None and inspect.isawaitable(val):
        return await val
    return val


def run_sync(coro: "Coroutine[Any, Any, _T]") -> _T:
    """Run an async coroutine from synchronous code, safely either way.

    ``asyncio.run`` (not the deprecated ``get_event_loop`` +
    ``run_until_complete``) creates and tears down its own loop, so this is
    safe on Python 3.12+, where ``get_event_loop`` raises once no loop has
    ever been set on the thread. When a loop is *already running* on this
    thread, ``asyncio.run`` would itself raise ``RuntimeError``; in that case
    the coroutine is driven to completion on a dedicated worker thread with
    its own fresh loop, which avoids the re-entrancy crash the old
    ``get_event_loop`` + ``run_until_complete`` pattern was prone to.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        running = False
    else:
        running = True

    if running:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()
    return asyncio.run(coro)


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

    async def _collect(self):
        items = []
        async for item in self.async_gen:
            items.append(item)
        return items

    def __iter__(self):
        # Drive the async generator to completion and return a plain iterator.
        return iter(run_sync(self._collect()))


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
