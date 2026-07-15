"""Small in-memory rate limiter and concurrency guards."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager


class ConcurrencyLimitExceeded(RuntimeError):
    """Raised when a concurrency guard has no free slots."""


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > self.window_seconds:
                events.popleft()
            if not events:
                self._events.pop(key, None)
                events = self._events[key]
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


class ConcurrencyLimit:
    def __init__(self, value: int) -> None:
        self._sem = threading.BoundedSemaphore(value)

    @contextmanager
    def hold(self):
        acquired = self._sem.acquire(blocking=False)
        if not acquired:
            raise ConcurrencyLimitExceeded("Too many concurrent requests")
        try:
            yield
        finally:
            self._sem.release()


class AsyncConcurrencyLimit:
    def __init__(self, value: int) -> None:
        self._value = value
        self._active = 0
        self._lock = asyncio.Lock()

    @property
    def active(self) -> int:
        return self._active

    async def acquire(self) -> None:
        async with self._lock:
            if self._active >= self._value:
                raise ConcurrencyLimitExceeded("Too many concurrent requests")
            self._active += 1

    def release(self) -> None:
        if self._active <= 0:
            raise RuntimeError("Concurrency limit released too many times")
        self._active -= 1

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.release()
