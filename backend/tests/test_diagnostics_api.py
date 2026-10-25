import json
import os
import sys
import urllib.error

import pandas as pd
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

import diagnostics_api  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app, base_url="http://127.0.0.1:8000")
DNS_FAILURE = urllib.error.URLError("[Errno 11001] getaddrinfo failed")


class FakeBroker:
    def __init__(self, name, configured=True, account=None, error=None):
        self.display_name = name
        self.configured = configured
        self.account = account or {"environment": "demo", "balances": [{"asset": "USDT", "free": 1000.0}]}
        self.error = error
        self.calls = []

    def is_configured(self, settings):
        return self.configured

    def get_account_summary(self, settings, execution_mode):
        self.calls.append(execution_mode)
        if self.error:
            raise self.error
        return self.account

    def execute_order(self, *args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("Connection checks must never place orders")


class FakeRegistry:
    def __init__(self, brokers):
        self.brokers = brokers

    def get(self, broker_id):
        return self.brokers[broker_id]


@pytest.fixture
def offline_world(monkeypatch):
    """Everything reachable and healthy unless a test says otherwise."""
    responses = {
        diagnostics_api.BINANCE_PING_URL: (200, b"{}"),
        diagnostics_api.AI_ENDPOINTS["groq"]: (200, json.dumps({"data": [{"id": "openai/gpt-oss-20b"}, {"id": "vision-x"}]}).encode()),
    }
    requested = []

    def fake_get(url, headers=None):
        requested.append((url, headers or {}))
        result = responses[url]
        if isinstance(result, Exception):
            raise result
        return result

    brokers = {
        "binance": FakeBroker("Binance", configured=False),
        "bitget": FakeBroker("Bitget"),
        "alpaca": FakeBroker("Alpaca", configured=False),
    }
    monkeypatch.setattr(diagnostics_api, "http_get", fake_get)
    monkeypatch.setattr(diagnostics_api, "broker_registry", FakeRegistry(brokers))
    monkeypatch.setattr(diagnostics_api, "resolve_api_keys", lambda settings: {"groq": "groq-key"})
    monkeypatch.setattr(diagnostics_api.market_data, "get_stock_data",
                        lambda *args: pd.DataFrame({"close": [1.0]}))
    return {"responses": responses, "brokers": brokers, "requested": requested}


SETTINGS = {"ai_provider": "groq", "ai_model": "", "ai_vision_model": "vision-x"}


def by_id(report):
    return {check["id"]: check for check in report["checks"]}


def test_healthy_setup_reports_every_connection(offline_world):
    checks = by_id(diagnostics_api.run_connection_checks(SETTINGS))

    assert checks["backend"]["status"] == "ok"
    assert checks["binance"]["status"] == "ok"
    assert checks["yahoo"]["status"] == "ok"
    assert checks["ai"]["status"] == "ok"
    assert "Vision model: vision-x" in checks["ai"]["message"]
    assert checks["broker_bitget"]["status"] == "ok"
    assert checks["broker_bitget"]["name"] == "Bitget (DEMO)"
    assert "1 balance found" in checks["broker_bitget"]["message"]
    assert checks["broker_binance"]["status"] == "skipped"
    assert checks["broker_alpaca"]["status"] == "skipped"
    assert all("elapsed_ms" in check for check in checks.values())


def test_brokers_are_checked_read_only_in_their_practice_environment(offline_world):
    offline_world["brokers"]["alpaca"].configured = True
    diagnostics_api.run_connection_checks(SETTINGS)

    assert offline_world["brokers"]["bitget"].calls == ["live"]  # follows the demo switch
    assert offline_world["brokers"]["alpaca"].calls == ["paper"]  # Alpaca's paper account
    assert offline_world["brokers"]["binance"].calls == []  # no keys -> not contacted


def test_unreachable_broker_is_explained_as_a_network_problem(offline_world):
    offline_world["brokers"]["bitget"].error = ValueError("Bitget network error: [Errno 11001] getaddrinfo failed")
    check = by_id(diagnostics_api.run_connection_checks(SETTINGS))["broker_bitget"]

    assert check["status"] == "error"
    assert "Can't reach Bitget" in check["message"]
    assert "DNS" in check["message"]
    assert "keys were not tested" in check["message"]


def test_wrong_demo_environment_gets_a_specific_hint(offline_world):
    offline_world["brokers"]["bitget"].error = ValueError("Bitget API error (40099): exchange environment is incorrect")
    check = by_id(diagnostics_api.run_connection_checks(SETTINGS))["broker_bitget"]

    assert check["status"] == "error"
    assert "demo key needs demo trading switched on" in check["message"]


def test_rejected_broker_key_is_reported(offline_world):
    offline_world["brokers"]["bitget"].error = ValueError("Bitget API error (40037): Apikey does not exist")
    check = by_id(diagnostics_api.run_connection_checks(SETTINGS))["broker_bitget"]

    assert check["status"] == "error"
    assert "rejected the request" in check["message"]


def test_ai_key_problems_and_missing_models(offline_world, monkeypatch):
    groq_url = diagnostics_api.AI_ENDPOINTS["groq"]
    offline_world["responses"][groq_url] = (401, b"")
    assert by_id(diagnostics_api.run_connection_checks(SETTINGS))["ai"]["status"] == "error"

    offline_world["responses"][groq_url] = (429, b"")
    assert by_id(diagnostics_api.run_connection_checks(SETTINGS))["ai"]["status"] == "warning"

    offline_world["responses"][groq_url] = (200, json.dumps({"data": [{"id": "openai/gpt-oss-20b"}]}).encode())
    check = by_id(diagnostics_api.run_connection_checks(SETTINGS))["ai"]
    assert check["status"] == "warning" and "vision-x" in check["message"]

    monkeypatch.setattr(diagnostics_api, "resolve_api_keys", lambda settings: {})
    check = by_id(diagnostics_api.run_connection_checks(SETTINGS))["ai"]
    assert check["status"] == "warning" and "No Groq API key" in check["message"]


def test_ai_key_is_sent_only_to_its_own_provider_and_never_reported(offline_world):
    report = diagnostics_api.run_connection_checks(SETTINGS)

    groq_headers = [h for url, h in offline_world["requested"] if url == diagnostics_api.AI_ENDPOINTS["groq"]]
    assert groq_headers == [{"Authorization": "Bearer groq-key"}]
    assert all(not h for url, h in offline_world["requested"] if url != diagnostics_api.AI_ENDPOINTS["groq"])
    assert "groq-key" not in json.dumps(report)


def test_dns_failures_are_explained(offline_world):
    offline_world["responses"][diagnostics_api.BINANCE_PING_URL] = DNS_FAILURE
    check = by_id(diagnostics_api.run_connection_checks(SETTINGS))["binance"]

    assert check["status"] == "error"
    assert "DNS" in check["message"]


def test_yahoo_rate_limit_is_a_warning(offline_world, monkeypatch):
    def limited(*args):
        raise RuntimeError("Too Many Requests. Rate limited. Try after a while.")

    monkeypatch.setattr(diagnostics_api.market_data, "get_stock_data", limited)
    check = by_id(diagnostics_api.run_connection_checks(SETTINGS))["yahoo"]
    assert check["status"] == "warning"


def test_one_failing_check_does_not_hide_the_others(offline_world):
    offline_world["brokers"]["bitget"].error = RuntimeError("unexpected")
    checks = by_id(diagnostics_api.run_connection_checks(SETTINGS))

    assert checks["broker_bitget"]["status"] == "error"
    assert checks["binance"]["status"] == "ok"


def test_endpoint_runs_checks_on_post_only(offline_world, monkeypatch):
    monkeypatch.setattr(diagnostics_api, "get_settings", lambda: SETTINGS)
    assert client.get("/api/diagnostics/connections").status_code == 405
    response = client.post("/api/diagnostics/connections")
    assert response.status_code == 200
    assert {check["id"] for check in response.json()["checks"]} >= {"backend", "binance", "yahoo", "ai", "broker_bitget"}
