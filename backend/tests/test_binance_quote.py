from backend.broker_integration.binance_broker import BinanceBroker


def test_binance_quote_maps_book_ticker_and_side_prices(monkeypatch):
    broker = BinanceBroker()
    monkeypatch.setattr(
        broker, "_public_request",
        lambda path, settings, params=None: {"bidPrice": "99.25", "askPrice": "100.75"},
    )

    quote = broker.get_quote("BTC/USDT", "crypto", {}, "live")

    assert quote.bid == 99.25
    assert quote.ask == 100.75
    assert quote.execution_reference("BUY") == 100.75
    assert quote.execution_reference("SELL") == 99.25
    assert "bookTicker" in quote.source
