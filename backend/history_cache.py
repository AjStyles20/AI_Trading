"""Short-lived shared cache for chart price history.

Every open copy of the app refreshes its chart on a timer, and each refresh
used to reach the data provider (Yahoo Finance), which then rate-limits the
user. Within a short window, requests for the same symbol, interval and period
share one provider result, and simultaneous requests wait for a single fetch
instead of each making their own.

Only the chart's history endpoint uses this cache. The trading loop fetches its
own data, so its decisions never use a cached frame. Failed fetches are never
cached.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable, Hashable

import pandas as pd

# Reuse window per interval; matches how often the chart refreshes it.
TTL_SECONDS_BY_INTERVAL = {"1m": 15, "5m": 30, "15m": 60, "30m": 60, "1h": 60, "4h": 120, "1d": 300}
DEFAULT_TTL_SECONDS = 60
MAX_ENTRIES = 64


class HistoryCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic, max_entries: int = MAX_ENTRIES):
        self._clock = clock
        self._max_entries = max_entries
        self._entries: OrderedDict[Hashable, tuple[float, pd.DataFrame]] = OrderedDict()
        self._lock = threading.Lock()
        self._key_locks: dict[Hashable, threading.Lock] = {}

    @staticmethod
    def ttl_for(interval: str) -> float:
        return TTL_SECONDS_BY_INTERVAL.get(interval, DEFAULT_TTL_SECONDS)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def get_or_fetch(self, key: Hashable, interval: str, fetch: Callable[[], pd.DataFrame]) -> pd.DataFrame:
        """Return a fresh-enough cached frame for `key`, or fetch, cache and return one.

        Callers get their own copy, so they can modify it freely.
        """
        with self._lock:
            key_lock = self._key_locks.setdefault(key, threading.Lock())
        # One fetch per key at a time: concurrent callers wait, then hit the cache.
        with key_lock:
            with self._lock:
                cached = self._entries.get(key)
                if cached and self._clock() - cached[0] < self.ttl_for(interval):
                    self._entries.move_to_end(key)
                    return cached[1].copy()
            frame = fetch()
            with self._lock:
                self._entries[key] = (self._clock(), frame)
                self._entries.move_to_end(key)
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)
            return frame.copy()
