import pytest

from core.position_ledger import reconstruct_confirmed_position


def trade(id, side, qty, price, *, symbol="BTC/USDT", broker="binance", mode="live", is_test=False):
    return {
        "id": id,
        "timestamp": f"2026-09-26 12:{id:02d}:00",
        "symbol": symbol,
        "broker_id": broker,
        "execution_mode": mode,
        "side": side,
        "filled_qty": qty,
        "filled_price": price,
        "is_test": is_test,
        "metadata": {},
    }


def test_position_ledger_weights_multiple_confirmed_entries():
    position = reconstruct_confirmed_position(
        [trade(1, "BUY", 1.0, 100.0), trade(2, "BUY", 2.0, 110.0)],
        symbol="BTC/USDT", broker_id="binance", execution_mode="live",
    )
    assert position.qty == pytest.approx(3.0)
    assert position.cost_basis == pytest.approx(320.0)
    assert position.average_entry_price == pytest.approx(320.0 / 3.0)


def test_position_ledger_consumes_partial_exit_fifo():
    position = reconstruct_confirmed_position(
        [
            trade(1, "BUY", 1.0, 100.0),
            trade(2, "BUY", 2.0, 110.0),
            trade(3, "SELL", 1.5, 120.0),
        ],
        symbol="BTC/USDT", broker_id="binance", execution_mode="live",
    )
    assert position.qty == pytest.approx(1.5)
    assert position.cost_basis == pytest.approx(165.0)
    assert position.average_entry_price == pytest.approx(110.0)


def test_position_ledger_full_exit_flattens_cost_basis():
    position = reconstruct_confirmed_position(
        [trade(1, "BUY", 1.25, 100.0), trade(2, "SELL", 1.25, 90.0)],
        symbol="BTC/USDT", broker_id="binance", execution_mode="live",
    )
    assert position.qty == 0.0
    assert position.cost_basis == 0.0
    assert position.average_entry_price == 0.0


def test_position_ledger_uses_current_cumulative_partial_fill_once():
    # One order row is updated in place from earlier fill states; the current
    # cumulative value must be counted once, not as multiple incremental fills.
    position = reconstruct_confirmed_position(
        [trade(1, "BUY", 1.25, 101.0)],
        symbol="BTC/USDT", broker_id="binance", execution_mode="live",
    )
    assert position.qty == pytest.approx(1.25)
    assert position.cost_basis == pytest.approx(126.25)


def test_position_ledger_isolates_symbol_broker_mode_and_test_orders():
    position = reconstruct_confirmed_position(
        [
            trade(1, "BUY", 1.0, 100.0),
            trade(2, "BUY", 5.0, 50.0, symbol="ETH/USDT"),
            trade(3, "BUY", 5.0, 50.0, broker="bitget"),
            trade(4, "BUY", 5.0, 50.0, mode="paper"),
            trade(5, "BUY", 5.0, 50.0, is_test=True),
        ],
        symbol="BTC/USDT", broker_id="binance", execution_mode="live",
    )
    assert position.qty == pytest.approx(1.0)
    assert position.average_entry_price == pytest.approx(100.0)


def test_position_ledger_rejects_oversold_history():
    with pytest.raises(ValueError, match="SELL fills exceed"):
        reconstruct_confirmed_position(
            [trade(1, "BUY", 1.0, 100.0), trade(2, "SELL", 1.5, 90.0)],
            symbol="BTC/USDT", broker_id="binance", execution_mode="live",
        )


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_position_ledger_rejects_nonpositive_confirmed_fill_price(side):
    history = [trade(1, "BUY", 1.0, 100.0)] if side == "SELL" else []
    history.append(trade(2, side, 0.5, 0.0))
    with pytest.raises(ValueError, match="positive filled_price"):
        reconstruct_confirmed_position(
            history,
            symbol="BTC/USDT", broker_id="binance", execution_mode="live",
        )


def test_position_ledger_rejects_unknown_filled_side():
    with pytest.raises(ValueError, match="Unsupported confirmed trade side"):
        reconstruct_confirmed_position(
            [trade(1, "SHORT", 1.0, 100.0)],
            symbol="BTC/USDT", broker_id="binance", execution_mode="live",
        )



def test_position_ledger_carries_surviving_entry_protection():
    first = trade(1, "BUY", 1.0, 100.0)
    first["metadata"] = {"stop_loss_pct": 2.0, "take_profit_pct": 4.0}
    position = reconstruct_confirmed_position(
        [first],
        symbol="BTC/USDT", broker_id="binance", execution_mode="live",
    )
    assert position.stop_loss_pct == pytest.approx(2.0)
    assert position.take_profit_pct == pytest.approx(4.0)


def test_position_ledger_preserves_protection_after_partial_fifo_exit():
    first = trade(1, "BUY", 1.0, 100.0)
    second = trade(2, "BUY", 2.0, 110.0)
    first["metadata"] = second["metadata"] = {"stop_loss_pct": 2.0, "take_profit_pct": 4.0}
    position = reconstruct_confirmed_position(
        [first, second, trade(3, "SELL", 1.5, 120.0)],
        symbol="BTC/USDT", broker_id="binance", execution_mode="live",
    )
    assert position.qty == pytest.approx(1.5)
    assert position.stop_loss_pct == pytest.approx(2.0)
    assert position.take_profit_pct == pytest.approx(4.0)


def test_position_ledger_rejects_conflicting_surviving_entry_protection():
    first = trade(1, "BUY", 1.0, 100.0)
    second = trade(2, "BUY", 1.0, 110.0)
    first["metadata"] = {"stop_loss_pct": 2.0, "take_profit_pct": 4.0}
    second["metadata"] = {"stop_loss_pct": 3.0, "take_profit_pct": 4.0}
    with pytest.raises(ValueError, match="conflicting protection parameters"):
        reconstruct_confirmed_position(
            [first, second],
            symbol="BTC/USDT", broker_id="binance", execution_mode="live",
        )


def test_position_ledger_flat_position_clears_protection():
    entry = trade(1, "BUY", 1.0, 100.0)
    entry["metadata"] = {"stop_loss_pct": 2.0, "take_profit_pct": 4.0}
    position = reconstruct_confirmed_position(
        [entry, trade(2, "SELL", 1.0, 105.0)],
        symbol="BTC/USDT", broker_id="binance", execution_mode="live",
    )
    assert position.stop_loss_pct == 0.0
    assert position.take_profit_pct == 0.0
