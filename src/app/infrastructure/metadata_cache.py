"""Bounded, thread-safe TTL cache for parsed media metadata."""

from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict


class MetadataCache:
    def __init__(self, *, ttl_seconds: int, max_entries: int) -> None:
        self.ttl_seconds = max(0, ttl_seconds)
        self.max_entries = max(0, max_entries)
        self._entries: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> dict | None:
        if not self.ttl_seconds or not self.max_entries:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            created_at, value = entry
            if now - created_at >= self.ttl_seconds:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return copy.deepcopy(value)

    def set(self, key: str, value: dict) -> None:
        if not self.ttl_seconds or not self.max_entries:
            return
        with self._lock:
            self._entries[key] = (time.monotonic(), copy.deepcopy(value))
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
