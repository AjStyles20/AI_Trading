import io
import json

import pytest

from backend.broker_integration import bitget_broker
from backend.broker_integration.bitget_broker import BitgetBroker

DEMO_SETTINGS = {
    "bitget_environment": "demo",
    "api_keys": {
        "bitget_key": "live-key", "bitget_secret": "live-secret", "bitget_passphrase": "live-pass",
        "bitget_demo_key": "demo-key", "bitget_demo_secret": "demo-secret", "bitget_demo_passphrase": "demo-pass",
    },
}
LIVE_SETTINGS = {**DEMO_SETTINGS, "bitget_environment": "live"}
SYMBOL_RULES = {"symbol": "BTCUSDT", "status": "online", "quantityPrecision": "6", "pricePrecision": "2",
                "minTradeUSDT": "1", "buyLimitPriceRatio": "0.02"}


@pytest.fixture
def captured(monkeypatch):
    """Capture outgoing Bitget requests instead of sending them."""
    requests = []

    def fake_urlopen(request, timeout=None):
        if "/public/symbols" in request.full_url:
            # Public symbol rules carry no keys; they are not an order request.
            return io.BytesIO(json.dumps({"code": "00000", "data": [SYMBOL_RULES]}).encode())
        requests.append(request)
        return io.BytesIO(json.dumps({"code": "00000", "data": []}).encode())

    # Keys come only from these settings, never from the environment or OS store.
    monkeypatch.setattr(bitget_broker, "resolve_api_keys", lambda settings: dict(settings.get("api_keys", {})))
    monkeypatch.setattr(bitget_broker.urllib.request, "urlopen", fake_urlopen)
    return requests


def _header(request, name):
    return {key.lower(): value for key, value in request.header_items()}.get(name.lower())


def test_demo_requests_use_demo_keys_and_the_demo_header(captured):
    BitgetBroker().get_account_summary(DEMO_SETTINGS, "live")

    assert len(captured) == 1
    request = captured[0]
    assert _header(request, "paptrading") == "1"
    assert _header(request, "ACCESS-KEY") == "demo-key"
    assert _header(request, "ACCESS-PASSPHRASE") == "demo-pass"


def test_live_requests_never_carry_the_demo_header(captured):
    BitgetBroker().get_account_summary(LIVE_SETTINGS, "live")

    request = captured[0]
    assert _header(request, "paptrading") is None
    assert _header(request, "ACCESS-KEY") == "live-key"


def test_demo_orders_are_routed_to_demo_trading(captured):
    from backend.broker_integration.base import BrokerOrder

    order = BrokerOrder(symbol="BTC/USDT", side="BUY", qty=0.001, price=80_000.0, asset_type="crypto",
                        metadata={"client_order_id": "astral-test-1"})
    BitgetBroker().execute_order(order, "live", DEMO_SETTINGS)

    request = captured[0]
    assert request.full_url.endswith("/api/v2/spot/trade/place-order")
    assert _header(request, "paptrading") == "1"
    assert _header(request, "ACCESS-KEY") == "demo-key"


def test_paper_mode_never_contacts_bitget(captured):
    BitgetBroker().get_account_summary(DEMO_SETTINGS, "paper")
    assert captured == []
