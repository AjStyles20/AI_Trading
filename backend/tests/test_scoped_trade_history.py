import json
import sqlite3

import database.sqlite_manager as sqlite_manager


def _create_trade_table(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, side TEXT, qty REAL, price REAL,
            broker_id TEXT, execution_mode TEXT, timestamp TEXT,
            is_paper INTEGER, order_status TEXT, order_type TEXT,
            broker_order_id TEXT, is_test INTEGER, metadata TEXT,
            requested_qty REAL, filled_qty REAL, filled_price REAL
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_trade(path, *, symbol, broker_id, execution_mode, timestamp, index):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        INSERT INTO trades (
            symbol, side, qty, price, broker_id, execution_mode, timestamp,
            is_paper, order_status, order_type, broker_order_id, is_test, metadata,
            requested_qty, filled_qty, filled_price
        ) VALUES (?, 'BUY', 1, 100, ?, ?, ?, 1, 'filled', 'market', ?, 0, ?, 1, 1, 100)
        """,
        (symbol, broker_id, execution_mode, timestamp, f"order-{index}", json.dumps({"index": index})),
    )
    conn.commit()
    conn.close()


def test_get_trades_for_scope_is_complete_ordered_and_isolated(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    _create_trade_table(db_path)
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))

    for index in range(125):
        _insert_trade(
            db_path,
            symbol="BTC/USDT",
            broker_id="paper",
            execution_mode="paper",
            timestamp=f"2026-09-{1 + index // 24:02d}T{index % 24:02d}:00:00Z",
            index=index,
        )

    _insert_trade(
        db_path, symbol="ETH/USDT", broker_id="paper", execution_mode="paper",
        timestamp="2026-09-01T00:00:00Z", index=1001,
    )
    _insert_trade(
        db_path, symbol="BTC/USDT", broker_id="binance", execution_mode="paper",
        timestamp="2026-09-01T00:00:00Z", index=1002,
    )
    _insert_trade(
        db_path, symbol="BTC/USDT", broker_id="paper", execution_mode="live",
        timestamp="2026-09-01T00:00:00Z", index=1003,
    )

    rows = sqlite_manager.get_trades_for_scope("BTC/USDT", "paper", "paper")

    assert len(rows) == 125
    assert [row["metadata"]["index"] for row in rows] == list(range(125))
    assert all(row["symbol"] == "BTC/USDT" for row in rows)
    assert all(row["broker_id"] == "paper" for row in rows)
    assert all(row["execution_mode"] == "paper" for row in rows)
