import backend.trading_api as trading_api


def _base_sell_trade():
    return {
        "id": 501,
        "symbol": "BTC/USDT",
        "side": "SELL",
        "qty": 1.0,
        "requested_qty": 1.0,
        "broker_id": "sandbox",
        "execution_mode": "live",
        "order_status": "submitted",
        "broker_order_id": "order-501",
        "metadata": {"cooldown_bars": 2, "interval": "1h"},
        "filled_qty": 0.0,
        "filled_price": 0.0,
        "is_test": False,
    }


def test_sandbox_soak_partial_fill_outage_recovery_and_single_terminal_transition(monkeypatch):
    responses = iter([
        {
            "order_status": "partially_filled",
            "broker_order_id": "order-501",
            "metadata": {"broker_reason": "PARTIAL_1"},
            "filled_qty": 0.25,
            "filled_price": 100.0,
        },
        RuntimeError("transient broker status outage"),
        {
            "order_status": "partially_filled",
            "broker_order_id": "order-501",
            "metadata": {"broker_reason": "PARTIAL_2"},
            "filled_qty": 0.75,
            "filled_price": 100.5,
        },
        {
            "order_status": "filled",
            "broker_order_id": "order-501",
            "metadata": {"broker_reason": "FILLED"},
            "filled_qty": 1.0,
            "filled_price": 101.0,
        },
    ])

    class ScriptedBroker:
        def get_order_status(self, trade, settings):
            item = next(responses)
            if isinstance(item, Exception):
                raise item
            return item

    persisted = []

    def persist(trade_id, status, broker_order_id, metadata, filled_qty=None, filled_price=None):
        persisted.append(
            {
                "id": trade_id,
                "status": status,
                "filled_qty": filled_qty,
                "filled_price": filled_price,
                "metadata": dict(metadata or {}),
            }
        )

    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: ScriptedBroker())
    monkeypatch.setattr(trading_api, "update_trade_order_state", persist)

    trades = [_base_sell_trade()]
    completed_exit_transitions = 0
    observed_fills = []

    # Poll 1: partial fill.
    trades = trading_api.reconcile_unresolved_orders(
        trades, {}, "BTC/USDT", "sandbox", "live"
    )
    observed_fills.append(trades[0]["filled_qty"])
    completed_exit_transitions += int(trades[0].get("_completed_exit_transition", False))
    assert trading_api.has_unresolved_order(trades, "BTC/USDT", "sandbox", "live") is True

    # Poll 2: broker outage. State must remain unresolved and retain prior fill truth.
    trades = trading_api.reconcile_unresolved_orders(
        trades, {}, "BTC/USDT", "sandbox", "live"
    )
    observed_fills.append(trades[0]["filled_qty"])
    completed_exit_transitions += int(trades[0].get("_completed_exit_transition", False))
    assert trades[0]["order_status"] == "partially_filled"
    assert trades[0]["filled_qty"] == 0.25
    assert "status_refresh_error" in trades[0]["metadata"]
    assert trading_api.has_unresolved_order(trades, "BTC/USDT", "sandbox", "live") is True

    # Poll 3: broker recovers with greater cumulative fill.
    trades = trading_api.reconcile_unresolved_orders(
        trades, {}, "BTC/USDT", "sandbox", "live"
    )
    observed_fills.append(trades[0]["filled_qty"])
    completed_exit_transitions += int(trades[0].get("_completed_exit_transition", False))
    assert trades[0]["filled_qty"] == 0.75
    assert trading_api.has_unresolved_order(trades, "BTC/USDT", "sandbox", "live") is True

    # Poll 4: terminal fill; exactly one completed SELL transition.
    trades = trading_api.reconcile_unresolved_orders(
        trades, {}, "BTC/USDT", "sandbox", "live"
    )
    observed_fills.append(trades[0]["filled_qty"])
    completed_exit_transitions += int(trades[0].get("_completed_exit_transition", False))
    assert trades[0]["order_status"] == "filled"
    assert trades[0]["filled_qty"] == 1.0
    assert trading_api.has_unresolved_order(trades, "BTC/USDT", "sandbox", "live") is False

    # Poll 5: terminal state must not query broker or emit a second exit transition.
    trades = trading_api.reconcile_unresolved_orders(
        trades, {}, "BTC/USDT", "sandbox", "live"
    )
    completed_exit_transitions += int(trades[0].get("_completed_exit_transition", False))

    assert observed_fills == sorted(observed_fills)
    assert observed_fills == [0.25, 0.25, 0.75, 1.0]
    assert completed_exit_transitions == 1
    assert [entry["filled_qty"] for entry in persisted] == [0.25, 0.75, 1.0]


def test_sandbox_soak_rejects_regressive_fill_without_persisting(monkeypatch):
    trade = _base_sell_trade()
    trade["order_status"] = "partially_filled"
    trade["filled_qty"] = 0.8
    trade["filled_price"] = 100.0

    class RegressiveBroker:
        def get_order_status(self, trade, settings):
            return {
                "order_status": "partially_filled",
                "broker_order_id": "order-501",
                "metadata": {"broker_reason": "STALE"},
                "filled_qty": 0.4,
                "filled_price": 100.0,
            }

    persisted = []
    monkeypatch.setattr(trading_api.broker_registry, "get", lambda broker_id: RegressiveBroker())
    monkeypatch.setattr(
        trading_api,
        "update_trade_order_state",
        lambda *args, **kwargs: persisted.append((args, kwargs)),
    )

    try:
        trading_api.reconcile_trade_order(trade, {})
    except ValueError as exc:
        assert "cumulative filled quantity regressed" in str(exc)
    else:
        raise AssertionError("Regressive cumulative fill must fail closed.")

    assert persisted == []
