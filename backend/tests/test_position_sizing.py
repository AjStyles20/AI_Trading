import pandas as pd

from backend.trading_api import resolve_strategy_quantity


def frame(position_size_pct=None):
    data = {"signal": [1]}
    if position_size_pct is not None:
        data["position_size_pct"] = [position_size_pct]
    return pd.DataFrame(data)


def test_buy_quantity_uses_strategy_pct_of_equity():
    qty = resolve_strategy_quantity(frame(20), "BUY", 100.0, 10_000.0, 0.0)
    assert qty == 20.0


def test_buy_quantity_defaults_to_conservative_ten_percent():
    qty = resolve_strategy_quantity(frame(), "BUY", 100.0, 10_000.0, 0.0)
    assert qty == 10.0


def test_invalid_strategy_pct_fails_closed():
    assert resolve_strategy_quantity(frame(0), "BUY", 100.0, 10_000.0, 0.0) == 0.0
    assert resolve_strategy_quantity(frame(101), "BUY", 100.0, 10_000.0, 0.0) == 0.0
    assert resolve_strategy_quantity(frame("bad"), "BUY", 100.0, 10_000.0, 0.0) == 0.0


def test_buy_requires_equity_and_positive_price():
    assert resolve_strategy_quantity(frame(20), "BUY", 100.0, None, 0.0) == 0.0
    assert resolve_strategy_quantity(frame(20), "BUY", 0.0, 10_000.0, 0.0) == 0.0


def test_sell_uses_current_position_and_never_invents_quantity():
    assert resolve_strategy_quantity(frame(20), "SELL", 100.0, 10_000.0, 3.5) == 3.5
    assert resolve_strategy_quantity(frame(20), "SELL", 100.0, 10_000.0, None) == 0.0
    assert resolve_strategy_quantity(frame(20), "SELL", 100.0, 10_000.0, 0.0) == 0.0
