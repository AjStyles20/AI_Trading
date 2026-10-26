"""Bitget Unified Trading Account (UTA) support: read-only for now."""
import io
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

import backend.trading_api as trading_api
from backend.broker_integration import bitget_broker
from backend.broker_integration.base import BrokerOrder
from backend.broker_integration.bitget_broker import BitgetBroker

KEYS = {
    "bitget_key": "live-key", "bitget_secret": "live-secret", "bitget_passphrase": "live-pass",
    "bitget_demo_key": "demo-key", "bitget_demo_secret": "demo-secret", "bitget_demo_passphrase": "demo-pass",
}
UNIFIED_DEMO = {"bitget_environment": "demo", "bitget_account_type": "unified", "api_keys": KEYS}
CLASSIC_DEMO = {"bitget_environment": "demo", "bitget_account_type": "classic", "api_keys": KEYS}

UTA_ASSETS = {
    "accountEquity": "4762170.08",
    "assets": [
        {"coin": "USDT", "equity": "50000", "usdValue": "50000", "balance": "50000", "available": "49000", "locked": "1000", "debt": "0"},
        {"coin": "BTC", "equity": "59.37", "usdValue": "4700000", "balance": "59.37", "available": "59.37", "locked": "0", "debt": "0"},
        {"coin": "ETH", "equity": "0", "usdValue": "0", "balance": "0", "available": "0", "locked": "0", "debt": "0"},
    ],
}
UTA_OPEN_ORDERS = {
    "list": [{
        "orderId": "111", "clientOid": "astral-1", "symbol": "BTCUSDT", "side": "buy", "orderType": "limit",
        "orderStatus": "partially_filled", "qty": "0.5", "cumExecQty": "0.2", "price": "79000", "createdTime": "1792900000000",
    }],
    "cursor": "111",
}


@pytest.fixture
def bitget_api(monkeypatch):
    """Answers Bitget requests from canned data and records every request."""
    requests = []
    routes = {
        "/api/v3/account/assets": UTA_ASSETS,
        "/api/v3/trade/unfilled-orders": UTA_OPEN_ORDERS,
        "/api/v2/spot/account/assets": [{"coin": "USDT", "available": "10", "frozen": "0"}],
    }

    def fake_urlopen(request, timeout=None):
        requests.append(request)
        path = urlparse(request.full_url).path
        return io.BytesIO(json.dumps({"code": "00000", "msg": "success", "data": routes[path]}).encode())

    monkeypatch.setattr(bitget_broker, "resolve_api_keys", lambda settings: dict(settings.get("api_keys", {})))
    monkeypatch.setattr(bitget_broker.urllib.request, "urlopen", fake_urlopen)
    return requests


def header(request, name):
    return {key.lower(): value for key, value in request.header_items()}.get(name.lower())


def test_unified_balances_come_from_the_v3_account_endpoint(bitget_api):
    summary = BitgetBroker().get_account_summary(UNIFIED_DEMO, "live")

    request = bitget_api[0]
    assert urlparse(request.full_url).path == "/api/v3/account/assets"
    assert header(request, "paptrading") == "1"
    assert header(request, "ACCESS-KEY") == "demo-key"
    assert summary["account_type"] == "unified"
    assert summary["environment"] == "demo"
    # Every non-zero coin with its USD value, largest first; zero balances dropped.
    assert summary["balances"] == [
        {"asset": "BTC", "free": 59.37, "locked": 0.0, "usd_value": 4700000.0},
        {"asset": "USDT", "free": 49000.0, "locked": 1000.0, "usd_value": 50000.0},
    ]
    assert summary["total_equity_usd"] == 4762170.08
    # Read-only until unified-account trading is verified.
    assert summary["can_trade"] is False


def test_classic_accounts_still_use_the_v2_spot_endpoint(bitget_api):
    summary = BitgetBroker().get_account_summary(CLASSIC_DEMO, "live")

    assert urlparse(bitget_api[0].full_url).path == "/api/v2/spot/account/assets"
    assert summary["account_type"] == "classic"
    assert summary["balances"] == [{"asset": "USDT", "free": 10.0, "locked": 0.0}]
    assert summary["can_trade"] is True


def test_account_type_defaults_to_classic(bitget_api):
    settings = {"bitget_environment": "demo", "api_keys": KEYS}
    BitgetBroker().get_account_summary(settings, "live")
    assert urlparse(bitget_api[0].full_url).path == "/api/v2/spot/account/assets"


def test_unified_positions_filter_by_symbol(bitget_api):
    positions = BitgetBroker().list_positions("BTC/USDT", "crypto", UNIFIED_DEMO, "live")

    assert [(p["symbol"], p["qty"], p["available_qty"]) for p in positions] == [("BTC", 59.37, 59.37)]


def test_unified_open_orders_use_v3_and_map_fields(bitget_api):
    orders = BitgetBroker().list_open_orders("BTC/USDT", "crypto", UNIFIED_DEMO, "live")

    request = bitget_api[0]
    assert urlparse(request.full_url).path == "/api/v3/trade/unfilled-orders"
    assert parse_qs(urlparse(request.full_url).query) == {"category": ["SPOT"], "symbol": ["BTCUSDT"]}
    assert orders == [{
        "broker_order_id": "111", "symbol": "BTCUSDT", "side": "BUY", "status": "partially_filled",
        "type": "limit", "orig_qty": 0.5, "executed_qty": 0.2, "price": 79000.0, "time": 1792900000000,
    }]


def test_paper_mode_never_contacts_bitget(bitget_api):
    broker = BitgetBroker()
    broker.get_account_summary(UNIFIED_DEMO, "paper")
    assert broker.list_positions("BTC/USDT", "crypto", UNIFIED_DEMO, "paper") == []
    assert broker.list_open_orders("BTC/USDT", "crypto", UNIFIED_DEMO, "paper") == []
    assert bitget_api == []


def buy():
    return BrokerOrder(symbol="BTC/USDT", side="BUY", qty=0.001, price=80000.0, asset_type="crypto",
                       metadata={"client_order_id": "astral-1"})


def test_unified_orders_are_refused_before_anything_is_sent(bitget_api):
    broker = BitgetBroker()
    with pytest.raises(ValueError, match="unified-account trading is not enabled"):
        broker.validate_order(buy(), "live", UNIFIED_DEMO)
    with pytest.raises(ValueError, match="unified-account trading is not enabled"):
        broker.execute_order(buy(), "live", UNIFIED_DEMO)
    with pytest.raises(ValueError, match="unified-account trading is not enabled"):
        broker.get_order_status({"broker_order_id": "111", "metadata": {}}, UNIFIED_DEMO)
    assert bitget_api == []


def test_guarded_submission_records_no_intent_for_unified_accounts(bitget_api, monkeypatch):
    monkeypatch.setattr(trading_api, "get_settings", lambda: {"autonomy_kill_switch": False})
    monkeypatch.setattr(trading_api.risk_engine, "evaluate_order", lambda **kwargs: SimpleNamespace(approved=True, reasons=[]))
    monkeypatch.setattr(trading_api, "record_trade",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not record an order intent")))

    with pytest.raises(ValueError, match="unified-account trading is not enabled"):
        trading_api.submit_guarded_order(
            broker=BitgetBroker(), order=buy(), settings=UNIFIED_DEMO, execution_mode="live",
            broker_id="bitget", account_equity=100_000.0, current_position_qty=0.0,
            day_start_equity=100_000.0, peak_equity=100_000.0,
        )
    assert bitget_api == []


def test_account_type_setting_is_stored_and_validated(tmp_path, monkeypatch):
    from database import sqlite_manager

    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "settings.db"))
    sqlite_manager.init_db()
    assert sqlite_manager.get_settings()["bitget_account_type"] == "classic"
    sqlite_manager.update_settings(bitget_account_type="unified")
    assert sqlite_manager.get_public_settings()["bitget_account_type"] == "unified"
    with pytest.raises(ValueError, match="bitget_account_type"):
        sqlite_manager.update_settings(bitget_account_type="portfolio")


def test_unified_summary_lists_every_coin_without_a_cap(bitget_api, monkeypatch):
    many = {"accountEquity": "1", "assets": [
        {"coin": f"C{i}", "balance": "1", "available": "1", "locked": "0", "usdValue": str(i)} for i in range(15)
    ]}
    monkeypatch.setattr(BitgetBroker, "_unified_account", lambda self, settings: many)
    summary = BitgetBroker().get_account_summary(UNIFIED_DEMO, "live")
    assert len(summary["balances"]) == 15
    assert summary["balances"][0]["asset"] == "C14"


def test_classic_summary_has_no_usd_values(bitget_api):
    summary = BitgetBroker().get_account_summary(CLASSIC_DEMO, "live")
    assert summary["total_equity_usd"] is None
    assert "usd_value" not in summary["balances"][0]
