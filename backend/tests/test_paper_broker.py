from backend.broker_integration.base import BrokerOrder
from backend.broker_integration.paper_broker import PaperBroker
from database import sqlite_manager


def order(side, qty, price=100.0, symbol="TEST"):
    return BrokerOrder(symbol=symbol, side=side, qty=qty, price=price, asset_type="stock", metadata={})


def test_paper_buy_updates_cash_and_position():
    broker = PaperBroker(starting_cash=1000)
    result = broker.execute_order(order("BUY", 2), "paper", {})
    account = broker.get_account_summary({}, "paper")
    assert result.status == "filled"
    assert account["cash"] == 800
    assert account["positions"][0]["qty"] == 2


def test_paper_rejects_insufficient_cash():
    broker = PaperBroker(starting_cash=100)
    result = broker.execute_order(order("BUY", 2), "paper", {})
    assert result.status == "rejected"
    assert broker.get_account_summary({}, "paper")["cash"] == 100


def test_paper_rejects_oversell():
    broker = PaperBroker(starting_cash=1000)
    broker.execute_order(order("BUY", 1), "paper", {})
    result = broker.execute_order(order("SELL", 2), "paper", {})
    assert result.status == "rejected"


def test_paper_round_trip_updates_equity():
    broker = PaperBroker(starting_cash=1000)
    broker.execute_order(order("BUY", 2, 100), "paper", {})
    broker.execute_order(order("SELL", 2, 110), "paper", {})
    account = broker.get_account_summary({}, "paper")
    assert account["cash"] == 1020
    assert account["equity"] == 1020
    assert account["positions"] == []



def test_paper_state_survives_new_broker_instance(tmp_path, monkeypatch):
    db_path = tmp_path / "paper-state.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))
    sqlite_manager.init_db()

    first = PaperBroker(starting_cash=1000)
    first.execute_order(order("BUY", 2, 100, "ABC"), "paper", {})
    first.execute_order(order("BUY", 1, 50, "XYZ"), "paper", {})

    restored = PaperBroker(starting_cash=999999)
    account = restored.get_account_summary({}, "paper")

    assert account["cash"] == 750
    assert account["equity"] == 1000
    positions = {item["symbol"]: item["qty"] for item in account["positions"]}
    assert positions == {"ABC": 2, "XYZ": 1}
    assert restored.starting_cash == 1000


def test_paper_reset_clears_persisted_risk_baseline(tmp_path, monkeypatch):
    db_path = tmp_path / "paper-reset.db"
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(db_path))
    sqlite_manager.init_db()

    broker = PaperBroker(starting_cash=1000)
    broker.execute_order(order("BUY", 2, 100, "ABC"), "paper", {})
    sqlite_manager.update_risk_equity_state("paper", "paper", 1000, trading_day="2026-09-26")
    assert sqlite_manager.get_risk_equity_state("paper", "paper") is not None

    broker.reset()

    restored = PaperBroker(starting_cash=1)
    account = restored.get_account_summary({}, "paper")
    assert account["cash"] == 1000
    assert account["positions"] == []
    assert sqlite_manager.get_risk_equity_state("paper", "paper") is None
