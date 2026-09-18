from __future__ import annotations

import copy
import time
from typing import Any, Callable


class TTLCache:
    def __init__(self, ttl_seconds: int = 600, max_size: int = 512):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._items: dict[str, tuple[float, Any]] = {}

    def get(self, key: str):
        item = self._items.get(key)
        if item is None:
            return None

        expires_at, value = item
        if expires_at <= time.monotonic():
            self._items.pop(key, None)
            return None

        return copy.deepcopy(value)

    def set(self, key: str, value: Any):
        if len(self._items) >= self.max_size and key not in self._items:
            oldest_key = min(self._items, key=lambda item: self._items[item][0])
            self._items.pop(oldest_key, None)

        self._items[key] = (time.monotonic() + self.ttl_seconds, copy.deepcopy(value))
        return value

    def get_or_set(self, key: str, loader: Callable[[], Any]):
        cached = self.get(key)
        if cached is not None:
            return cached, True

        value = loader()
        self.set(key, value)
        return copy.deepcopy(value), False

    def clear(self):
        self._items.clear()
