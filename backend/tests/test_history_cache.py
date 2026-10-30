import os
import sys
import threading
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

from backend.history_cache import HistoryCache  # noqa: E402
import data_api  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app, base_url="http://127.0.0.1:8000")


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


def frame(close=101.0):
    return pd.DataFrame(
        {"open": [100.0], "high": [102.0], "low": [99.0], "close": [close], "volume": [5.0]},
        index=pd.DatetimeIndex(["2026-10-24T00:00:00Z"], name="timestamp"),
    )


class Provider:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return result


def test_reuses_a_recent_result_within_the_interval_window():
    clock = Clock()
    cache = HistoryCache(clock=clock)
    provider = Provider(frame(101.0), frame(202.0))

    assert cache.get_or_fetch("k", "1m", provider)["close"].iloc[-1] == 101.0
    clock.now += 14
    assert cache.get_or_fetch("k", "1m", provider)["close"].iloc[-1] == 101.0
    assert provider.calls == 1

    clock.now += 2  # 16 s > the 15 s window for 1m
    assert cache.get_or_fetch("k", "1m", provider)["close"].iloc[-1] == 202.0
    assert provider.calls == 2


def test_windows_follow_the_interval():
    assert HistoryCache.ttl_for("1m") == 15
    assert HistoryCache.ttl_for("1h") == 60
    assert HistoryCache.ttl_for("1d") == 300
    assert HistoryCache.ttl_for("weird") == 60


def test_different_symbols_or_intervals_never_share_results():
    cache = HistoryCache(clock=Clock())
    first, second = Provider(frame(1.0)), Provider(frame(2.0))
    cache.get_or_fetch(("stock", "AAPL", "1h", None), "1h", first)
    result = cache.get_or_fetch(("stock", "NVDA", "1h", None), "1h", second)
    assert result["close"].iloc[-1] == 2.0
    assert (first.calls, second.calls) == (1, 1)


def test_failures_are_not_cached():
    cache = HistoryCache(clock=Clock())
    provider = Provider(RuntimeError("rate limited"), frame(101.0))
    with pytest.raises(RuntimeError):
        cache.get_or_fetch("k", "1h", provider)
    assert cache.get_or_fetch("k", "1h", provider)["close"].iloc[-1] == 101.0
    assert provider.calls == 2


def test_callers_get_independent_copies():
    cache = HistoryCache(clock=Clock())
    provider = Provider(frame(101.0))
    mine = cache.get_or_fetch("k", "1h", provider)
    mine.index = mine.index.tz_localize(None) if mine.index.tz else mine.index
    mine["close"] = 0.0
    assert cache.get_or_fetch("k", "1h", provider)["close"].iloc[-1] == 101.0


def test_simultaneous_requests_share_one_fetch():
    cache = HistoryCache()
    calls = []

    def slow_fetch():
        calls.append(1)
        time.sleep(0.2)
        return frame(101.0)

    results = []
    threads = [threading.Thread(target=lambda: results.append(cache.get_or_fetch("k", "1h", slow_fetch))) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(calls) == 1
    assert len(results) == 5


def test_least_recently_used_entries_are_dropped_beyond_the_limit():
    cache = HistoryCache(clock=Clock(), max_entries=2)
    providers = {key: Provider(frame()) for key in "abc"}
    for key in "abc":
        cache.get_or_fetch(key, "1h", providers[key])
    cache.get_or_fetch("a", "1h", providers["a"])  # evicted, fetched again
    cache.get_or_fetch("c", "1h", providers["c"])  # still cached
    assert providers["a"].calls == 2
    assert providers["c"].calls == 1


def test_history_endpoint_shares_provider_calls_between_requests(monkeypatch):
    monkeypatch.setattr(data_api, "history_cache", HistoryCache())
    provider_calls = []
    monkeypatch.setattr(data_api.market_data, "get_stock_data",
                        lambda *args, **kwargs: provider_calls.append(args) or frame(101.0))
    payload = {"symbol": "AAPL", "asset_type": "stock", "interval": "1h", "limit": 5}

    first = client.post("/api/market/history", json=payload)
    second = client.post("/api/market/history", json={**payload, "symbol": "aapl", "limit": 1})

    assert first.status_code == second.status_code == 200
    assert first.json()[0]["close"] == second.json()[0]["close"] == 101.0
    assert len(provider_calls) == 1
