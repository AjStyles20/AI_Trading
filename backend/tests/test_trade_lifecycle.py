from database import sqlite_manager


def test_trade_lifecycle_preserves_request_and_tracks_fills(tmp_path, monkeypatch):
    db_path = tmp_path / "trade-lifecycle.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))
    sqlite_manager.init_db()

    sqlite_manager.record_trade(
        symbol="AAPL",
        side="BUY",
        qty=1.0,
        price=100.0,
        broker_id="alpaca",
        execution_mode="live",
        order_status="accepted",
        broker_order_id="order-123",
        requested_qty=1.0,
        filled_qty=0.0,
        filled_price=0.0,
        metadata={"executed_qty": 0.0},
    )
    trade = sqlite_manager.get_trades(limit=1)[0]
    assert trade["qty"] == 1.0

    sqlite_manager.update_trade_order_state(
        trade["id"],
        "partially_filled",
        "order-123",
        {"executed_qty": 0.4, "filled_avg_price": 101.25},
        filled_qty=0.4,
        filled_price=101.25,
    )

    sqlite_manager.update_trade_order_state(
        trade["id"],
        "filled",
        "order-123",
        {"executed_qty": 1.0, "filled_avg_price": 102.5},
        filled_qty=1.0,
        filled_price=102.5,
    )

    conn = sqlite_manager.sqlite3.connect(sqlite_manager.DB_PATH)
    row = conn.execute(
        "SELECT requested_qty, filled_qty, filled_price, order_status FROM trades WHERE id = ?",
        (trade["id"],),
    ).fetchone()
    conn.close()

    assert row == (1.0, 1.0, 102.5, "filled")


def test_cancelled_partial_fill_preserves_execution_state(tmp_path, monkeypatch):
    db_path = tmp_path / "trade-cancel.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))
    sqlite_manager.init_db()

    sqlite_manager.record_trade(
        symbol="BTCUSDT",
        side="BUY",
        qty=2.0,
        price=100.0,
        broker_id="binance",
        execution_mode="live",
        order_status="partially_filled",
        broker_order_id="order-456",
        requested_qty=2.0,
        filled_qty=0.5,
        filled_price=100.0,
        metadata={"executed_qty": 0.5},
    )
    trade = sqlite_manager.get_trades(limit=1)[0]

    sqlite_manager.update_trade_order_state(
        trade["id"],
        "canceled",
        "order-456",
        {"executedQty": "0.5", "cummulativeQuoteQty": "50.0"},
        filled_qty=0.5,
        filled_price=100.0,
    )

    persisted = sqlite_manager.get_trade_by_id(trade["id"])
    assert persisted["requested_qty"] == 2.0
    assert persisted["filled_qty"] == 0.5
    assert persisted["filled_price"] == 100.0
    assert persisted["order_status"] == "canceled"
