"""Connection checks behind Settings -> "Test connections".

Each check reports ok / warning / error / skipped with a plain-language
message. Everything is read-only: market data and AI endpoints are pinged, and
brokers get a balance lookup in the environment the user configured (demo or
testnet when switched on, Alpaca's paper account). No orders are ever sent,
and no key material is ever included in a result.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from fastapi import APIRouter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.broker_integration.registry import broker_registry
from core.credential_provider import resolve_api_keys
from core.data_service import market_data
from database.sqlite_manager import get_settings

router = APIRouter()

TIMEOUT_SECONDS = 10
BINANCE_PING_URL = "https://data-api.binance.vision/api/v3/ping"
AI_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/models",
    "groq": "https://api.groq.com/openai/v1/models",
    "ollama": "http://127.0.0.1:11434/api/tags",
}
AI_DEFAULT_MODELS = {"openai": "gpt-4.1-mini", "groq": "openai/gpt-oss-20b", "ollama": ""}
AI_NAMES = {"openai": "OpenAI", "groq": "Groq", "ollama": "Ollama"}
# Brokers are checked in the practice environment where one exists.
BROKER_CHECK_MODE = {"binance": "live", "bitget": "live", "alpaca": "paper"}


def _result(check_id: str, name: str, status: str, message: str) -> dict:
    return {"id": check_id, "name": name, "status": status, "message": message}


def describe_network_problem(reason: object) -> str:
    text = str(reason)
    lowered = text.lower()
    if "getaddrinfo" in lowered or "name or service not known" in lowered or "nodename nor servname" in lowered:
        return "its address could not be looked up (a DNS problem on this computer or network)"
    if "timed out" in lowered or "timeout" in lowered:
        return "the connection timed out"
    if "refused" in lowered:
        return "the connection was refused"
    return text or "the network request failed"


def http_get(url: str, headers: dict | None = None) -> tuple[int, bytes]:
    """GET returning (status, body); raises urllib.error.URLError when unreachable."""
    request = urllib.request.Request(url, headers={"User-Agent": "AstralAI/1.0", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if hasattr(exc, "read") else b""


def check_binance() -> dict:
    name = "Binance live prices"
    try:
        status, _ = http_get(BINANCE_PING_URL)
    except urllib.error.URLError as exc:
        return _result("binance", name, "error",
                       f"Can't reach Binance from this computer: {describe_network_problem(exc.reason)}. "
                       "Crypto charts fall back to Yahoo, without live streaming.")
    if status == 200:
        return _result("binance", name, "ok", "Reachable. Crypto charts can stream live from Binance.")
    if status == 429:
        return _result("binance", name, "warning", "Binance is limiting requests from your connection; try again shortly.")
    return _result("binance", name, "error", f"Binance answered HTTP {status}.")


def check_yahoo() -> dict:
    name = "Yahoo Finance (stocks)"
    try:
        frame = market_data.get_stock_data("AAPL", "1d", "5d")
    except Exception as exc:  # MarketDataError or provider failure
        text = str(exc)
        if "429" in text or "too many" in text.lower() or "rate" in text.lower():
            return _result("yahoo", name, "warning", "Yahoo is rate-limiting your connection; stock charts may fail for a while.")
        return _result("yahoo", name, "error", f"Stock prices could not be loaded: {text}")
    if frame is None or frame.empty:
        return _result("yahoo", name, "warning", "Yahoo returned no data; it may be rate-limiting your connection.")
    return _result("yahoo", name, "ok", "Stock prices load normally.")


def check_ai(settings: dict) -> dict:
    provider = settings.get("ai_provider", "openai")
    label = AI_NAMES.get(provider, provider)
    name = f"AI ({label})"
    model = settings.get("ai_model") or AI_DEFAULT_MODELS.get(provider, "")
    vision_model = settings.get("ai_vision_model") or ""
    if provider == "ollama":
        headers = {}
        if not model:
            return _result("ai", name, "warning", "No Ollama model is set. Enter one under Settings -> Model.")
    else:
        key = resolve_api_keys(settings).get(provider)
        if not key:
            return _result("ai", name, "warning", f"No {label} API key is saved. Add it in Settings.")
        headers = {"Authorization": f"Bearer {key}"}
    try:
        status, body = http_get(AI_ENDPOINTS[provider], headers)
    except urllib.error.URLError as exc:
        where = "Ollama on this computer (is it running?)" if provider == "ollama" else label
        return _result("ai", name, "error", f"Can't reach {where}: {describe_network_problem(exc.reason)}.")
    if status in (401, 403):
        return _result("ai", name, "error", f"{label} rejected the API key. Create a new key and save it in Settings.")
    if status == 429:
        return _result("ai", name, "warning", f"{label} is rate-limiting you (free-tier limits); try again later.")
    if status != 200:
        return _result("ai", name, "error", f"{label} answered HTTP {status}.")
    try:
        payload = json.loads(body or b"{}")
        items = payload.get("data") or payload.get("models") or []
        available = {item.get("id") or item.get("name") for item in items if isinstance(item, dict)}
    except ValueError:
        available = set()
    missing = [m for m in (model, vision_model) if m and available and m not in available and f"{m}:latest" not in available]
    if missing:
        return _result("ai", name, "warning", f"Key works, but {label} doesn't list: {', '.join(missing)}. Check the model name in Settings.")
    vision_note = f" Vision model: {vision_model}." if vision_model else " No vision model set (needed for images)." if provider != "openai" else ""
    return _result("ai", name, "ok", f"Connected; model {model} is available.{vision_note}")


def check_broker(broker_id: str, settings: dict) -> dict:
    broker = broker_registry.get(broker_id)
    name = broker.display_name
    check_id = f"broker_{broker_id}"
    if not broker.is_configured(settings):
        return _result(check_id, name, "skipped", "No keys saved, so not checked.")
    mode = BROKER_CHECK_MODE.get(broker_id, "live")
    try:
        account = broker.get_account_summary(settings, mode)
    except ValueError as exc:
        text = str(exc)
        if "network error" in text:
            reason = text.split("network error:", 1)[-1].strip()
            return _result(check_id, name, "error",
                           f"Can't reach {name} from this computer: {describe_network_problem(reason)}. The keys were not tested.")
        if "40099" in text:
            return _result(check_id, name, "error",
                           f"{name} says the environment is wrong: a demo key needs demo trading switched on (and a live key needs it off).")
        return _result(check_id, name, "error", f"{name} rejected the request: {text}")
    environment = str(account.get("environment") or mode).upper()
    account_type = account.get("account_type")
    label = f"{name} ({environment}{f', {account_type}' if account_type else ''})"
    balances = account.get("balances") or []
    if not balances and account_type == "classic":
        # A unified Bitget account answers classic balance requests with nothing.
        return _result(check_id, label, "warning",
                       "Keys accepted, but no balances found. If this is a Bitget Unified account, set "
                       "Settings -> Bitget account type to Unified and test again.")
    holdings = f"{len(balances)} balance{'s' if len(balances) != 1 else ''} found" if balances else "keys accepted; the account holds no balances"
    return _result(check_id, label, "ok", f"Read-only balance check passed: {holdings}.")


def run_connection_checks(settings: dict, timer: Callable[[], float] = time.monotonic) -> dict:
    checks: list[tuple[str, Callable[[], dict]]] = [
        ("binance", check_binance),
        ("yahoo", check_yahoo),
        ("ai", lambda: check_ai(settings)),
    ]
    checks += [(f"broker_{broker_id}", lambda b=broker_id: check_broker(b, settings)) for broker_id in BROKER_CHECK_MODE]

    def timed(item: tuple[str, Callable[[], dict]]) -> dict:
        check_id, check = item
        started = timer()
        try:
            result = check()
        except Exception as exc:  # A failing check must not hide the others.
            result = _result(check_id, check_id, "error", f"The check itself failed: {exc}")
        result["elapsed_ms"] = int((timer() - started) * 1000)
        return result

    with ThreadPoolExecutor(max_workers=len(checks)) as pool:
        results = list(pool.map(timed, checks))
    backend = _result("backend", "Astral backend", "ok", "Running and answering.")
    backend["elapsed_ms"] = 0
    return {
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "checks": [backend, *results],
    }


@router.post("/api/diagnostics/connections")
def connection_checks():
    """Runs read-only connection checks; only when the user asks (POST)."""
    return run_connection_checks(get_settings() or {})


def build_diagnostics_report() -> str:
    """A plain-text summary for the user to copy when asking for help.

    Local facts only; nothing is sent anywhere. Credentials appear by name and
    presence only, and the home folder is replaced with ~.
    """
    import platform
    import sqlite3

    from core.credential_provider import credential_presence
    from database import sqlite_manager

    def scrub(text: str) -> str:
        home = os.path.expanduser("~")
        return text.replace(home, "~") if home and home != "~" else text

    settings = get_settings() or {}
    lines = [
        "Astral AI diagnostics report",
        f"Created: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"App version: {_app_version()}",
        f"Platform: {platform.system()} {platform.release()} ({platform.machine()}), Python {platform.python_version()}",
        f"Data folder: {scrub(os.path.dirname(sqlite_manager.DB_PATH))}",
        "",
        "Safety",
        f"- Kill switch armed: {bool(settings.get('autonomy_kill_switch', True))}",
        f"- Live trading enabled: {bool(settings.get('risk_live_trading_enabled', False))}",
        f"- Max order notional: {settings.get('risk_max_order_notional')}",
        "",
        "Configuration",
        f"- AI provider: {settings.get('ai_provider') or 'none'}",
        f"- Binance environment: {settings.get('binance_environment')}, Bitget environment: {settings.get('bitget_environment')}",
    ]
    try:
        stored = sorted(name for name, present in credential_presence(settings).items() if present)
    except Exception:
        stored = ["(could not be read)"]
    lines.append(f"- Stored credentials (names only): {', '.join(stored) or 'none'}")
    try:
        with open(os.path.join(os.path.dirname(sqlite_manager.DB_PATH), "phone_gateway.json"), encoding="utf-8") as handle:
            phone = "on" if json.load(handle).get("host") else "off"
    except (OSError, ValueError):
        phone = "off"
    lines.append(f"- Phone access: {phone}")

    lines += ["", "Records"]
    conn = sqlite3.connect(sqlite_manager.DB_PATH)
    try:
        for table in ("trades", "strategies", "price_alerts", "chat_logs", "trading_journal", "phone_devices"):
            try:
                count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                count = "missing"
            lines.append(f"- {table}: {count}")
    finally:
        conn.close()

    lines += ["", "Last journal lines (UTC)"]
    journal = sqlite_manager.get_journal_entries(15)
    lines += [f"- {e['created_at']} {scrub(e['message'])}" for e in reversed(journal)] or ["- none"]
    lines += ["", "Last settings changes (UTC)"]
    audit = sqlite_manager.get_audit_events(10)
    lines += [f"- {e['created_at']} {e['category']} {e['action']}: {json.dumps(e['details'])}" for e in audit] or ["- none"]
    return "\n".join(lines) + "\n"


def _app_version() -> str:
    try:
        from main import app
        return app.version
    except Exception:
        return "unknown"


@router.get("/api/diagnostics/report")
def diagnostics_report():
    return {"report": build_diagnostics_report()}
