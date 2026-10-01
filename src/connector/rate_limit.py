"""Small async client-side limiter used before requests and during retries."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class RateLimiter:
    """Serialize request starts and enforce a minimum spacing between them."""

    def __init__(
        self,
        min_interval: float = 0.0,
        *,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        self.min_interval = max(0.0, min_interval)
        self._sleep = sleep
        self._clock = clock
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = self._clock()
            wait_for = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self.min_interval
        if wait_for:
            await self._sleep(wait_for)

    async def wait(self, seconds: float) -> None:
        if seconds > 0:
            await self._sleep(seconds)
