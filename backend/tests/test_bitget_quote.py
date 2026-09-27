from backend.broker_integration.bitget_broker import BitgetBroker


def test_bitget_quote_maps_spot_ticker_and_side_prices(monkeypatch):
    broker = BitgetBroker()
    monkeypatch.setattr(
        broker, "_request",
        lambda *args, **kwargs: [{
            "bidPr": "99.10", "askPr": "100.90", "lastPr": "100.00", "ts": "1790500000000"
        }],
    )

    quote = broker.get_quote("BTC/USDT", "crypto", {}, "live")

    assert quote.bid == 99.10
    assert quote.ask == 100.90
    assert quote.last == 100.00
    assert quote.timestamp == "1790500000000"
    assert quote.execution_reference("BUY") == 100.90
    assert quote.execution_reference("SELL") == 99.10
