"""Thread-safe bounded in-process L1 TTL cache for short-lived API & graph projections."""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from typing import Any


class LocalTTLCache:
    """Bounded LRU + TTL JSON cache used when Redis L2 is disabled or unavailable."""

    def __init__(self, *, max_items: int = 4096) -> None:
        self._max_items = max(64, max_items)
        self._lock = threading.RLock()
        self._store: OrderedDict[str, tuple[float, bytes]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, raw = entry
            if expires_at <= now:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
        return json.loads(raw.decode("utf-8"))

    def set(self, key: str, value: Any, *, ttl_seconds: int = 20) -> bool:
        try:
            payload = json.dumps(value, default=str).encode("utf-8")
        except Exception:
            return False
        expires_at = time.monotonic() + max(1, int(ttl_seconds))
        with self._lock:
            self._store[key] = (expires_at, payload)
            self._store.move_to_end(key)
            while len(self._store) > self._max_items:
                self._store.popitem(last=False)
        return True

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def invalidate_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                self._store.pop(k, None)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


local_response_cache = LocalTTLCache(max_items=4096)
