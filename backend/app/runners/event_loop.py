"""Run async Playwright work off the uvicorn event loop (Windows subprocess fix)."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")

_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="qeos-async-runner")


def run_async_in_new_loop(coro: Awaitable[T]) -> T:
    """Execute a coroutine in a fresh event loop (Proactor on Windows)."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def run_isolated_async(
    factory: Callable[[], Awaitable[T]],
    *,
    replay_events: list[dict] | None = None,
    on_event: Callable[[dict], Awaitable[None] | None] | None = None,
) -> T:
    """
    Run async Playwright code in a worker thread with its own loop.
    Optionally replay collected navigation events on the caller loop.
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_executor, lambda: run_async_in_new_loop(factory()))
    if replay_events and on_event:
        for event in replay_events:
            cb = on_event(event)
            if cb is not None and hasattr(cb, "__await__"):
                await cb
    return result
