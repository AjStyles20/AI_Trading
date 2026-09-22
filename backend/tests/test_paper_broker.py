from backend.broker_integration.base import BrokerOrder
from backend.broker_integration.paper_broker import PaperBroker


def order(side, qty, price=100.0, symbol="TEST"):
    return BrokerOrder(symbol=symbol, side=side, qty=qty, price=price)


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
