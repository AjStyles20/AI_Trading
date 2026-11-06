import json
import os
import sys

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as GatewayClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
import phone_gateway  # noqa: E402
from database import sqlite_manager  # noqa: E402

desktop = TestClient(main.app, base_url="http://127.0.0.1:8000")


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_manager, "DB_PATH", str(tmp_path / "phone.db"))
    sqlite_manager.init_db()


@pytest.fixture
def dist(tmp_path):
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text("<html>astral</html>")
    (folder / "assets" / "app.js").write_text("console.log('app')")
    (tmp_path / "secret.txt").write_text("outside the app")
    return folder


@pytest.fixture
def forwarded():
    return []


@pytest.fixture
def gateway(dist, forwarded):
    def fake_forward(method, path, headers, body):
        forwarded.append({"method": method, "path": path, "headers": headers, "body": body})
        return 200, json.dumps({"ok": True}).encode(), "application/json"

    app = phone_gateway.create_gateway_app(forward=fake_forward, dist_dir=str(dist), desktop_token="desk-tok")
    return GatewayClient(app, base_url="http://100.101.102.103:8765")


def paired(gateway):
    token = sqlite_manager.create_phone_device("My phone")["token"]
    assert gateway.post("/pair", json={"token": token}).status_code == 200
    return token


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "100.64.0.1", "100.101.102.103", "100.127.255.254"])
def test_listens_only_on_tailscale_or_this_computer(host):
    assert phone_gateway.check_bind_address(host) == host


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "10.0.0.5", "100.128.0.1", "8.8.8.8", "localhost", "my-pc"])
def test_refuses_every_other_address(host):
    with pytest.raises(ValueError):
        phone_gateway.check_bind_address(host)


def test_an_unpaired_phone_gets_nothing(gateway, forwarded):
    assert gateway.get("/api/trading/status").status_code == 401
    response = gateway.get("/", follow_redirects=False)
    assert response.status_code == 302 and response.headers["location"] == "/pair"
    assert gateway.get("/assets/app.js").status_code == 401
    assert gateway.post("/phone/arm").status_code == 401
    assert gateway.post("/pair", json={"token": "made-up"}).status_code == 401
    assert forwarded == []


def test_a_paired_phone_reads_and_requests_carry_no_phone_secrets(gateway, forwarded):
    paired(gateway)

    response = gateway.get("/api/trading/status", headers={"Origin": "http://100.101.102.103:8765", "Sec-Fetch-Site": "same-origin"})
    assert response.status_code == 200
    sent = forwarded[-1]
    assert sent["path"] == "/api/trading/status"
    assert sent["headers"].get("x-astral-desktop-token") == "desk-tok"
    lowered = {key.lower() for key in sent["headers"]}
    assert not lowered & {"cookie", "origin", "sec-fetch-site", "host"}

    assert gateway.post("/api/market/history", json={"symbol": "GC=F"}).status_code == 200
    assert json.loads(forwarded[-1]["body"]) == {"symbol": "GC=F"}
    assert gateway.get("/api/market/quote/stock/GC%3DF").status_code == 200
    assert gateway.get("/api/trading/journal?limit=5").status_code == 200
    assert forwarded[-1]["path"] == "/api/trading/journal?limit=5"


@pytest.mark.parametrize("method, path", [
    ("POST", "/api/trading/toggle"),
    ("POST", "/api/trading/test-order"),
    ("POST", "/api/trading/cancel-order"),
    ("POST", "/api/trading/kill-switch/disarm"),
    ("POST", "/api/settings"),
    ("POST", "/api/chat"),
    ("POST", "/api/alerts"),
    ("DELETE", "/api/alerts/1"),
    ("POST", "/api/backups"),
    ("GET", "/api/backups"),
    ("GET", "/api/research/sentiment/AAPL"),
    ("GET", "/api/ai/memory"),
    ("GET", "/api/phone/devices"),
    ("POST", "/api/phone/devices"),
    ("GET", "/api/trading/history/refresh"),
    ("GET", "/api/settings/../trading/toggle"),
    ("GET", "/api/trading/status/extra"),
])
def test_everything_off_the_allowlist_is_refused(gateway, forwarded, method, path):
    paired(gateway)
    response = gateway.request(method, path, json={} if method != "GET" else None)
    assert response.status_code in (403, 404, 405)
    assert all(item["path"].split("?")[0] != path for item in forwarded)
    assert not any("toggle" in item["path"] or "disarm" in item["path"] for item in forwarded)


def test_arming_is_the_only_action_and_sends_exactly_arm(gateway, forwarded):
    paired(gateway)
    assert gateway.post("/phone/arm", json={"autonomy_kill_switch": False}).status_code == 200

    sent = forwarded[-1]
    assert (sent["method"], sent["path"]) == ("POST", "/api/settings")
    assert json.loads(sent["body"]) == {"autonomy_kill_switch": True}


def test_a_revoked_phone_is_locked_out(gateway):
    token = paired(gateway)
    device_id = sqlite_manager.list_phone_devices()[0]["id"]
    assert gateway.get("/api/trading/status").status_code == 200

    sqlite_manager.revoke_phone_device(device_id)

    assert gateway.get("/api/trading/status").status_code == 401
    assert gateway.post("/pair", json={"token": token}).status_code == 401


def test_app_files_are_served_but_nothing_outside_them(gateway):
    paired(gateway)
    assert gateway.get("/").text == "<html>astral</html>"
    assert gateway.get("/assets/app.js").text == "console.log('app')"
    assert "outside the app" not in gateway.get("/../secret.txt").text
    assert "outside the app" not in gateway.get("/assets/..%2F..%2Fsecret.txt").text


def test_tokens_are_stored_only_as_hashes():
    device = sqlite_manager.create_phone_device("Tablet")
    raw = open(sqlite_manager.DB_PATH, "rb").read()
    assert device["token"].encode() not in raw
    assert "token" not in sqlite_manager.list_phone_devices()[0]


def test_desktop_pairs_lists_and_revokes_phones_with_an_audit_trail():
    created = desktop.post("/api/phone/devices", json={"name": "Pixel"}).json()
    assert len(created["token"]) >= 40

    listed = desktop.get("/api/phone/devices").json()["items"]
    assert listed[0]["name"] == "Pixel" and "token" not in listed[0]

    assert desktop.delete(f"/api/phone/devices/{created['id']}").status_code == 200
    assert desktop.delete(f"/api/phone/devices/{created['id']}").status_code == 404
    assert [e["action"] for e in sqlite_manager.get_audit_events(5)][:2] == ["revoked", "paired"]
    assert all(created["token"] not in json.dumps(e) for e in sqlite_manager.get_audit_events(5))


@pytest.mark.parametrize("name", ["", "x" * 41, "<script>"])
def test_device_names_are_validated(name):
    assert desktop.post("/api/phone/devices", json={"name": name}).status_code == 422


def test_the_apps_own_arm_request_passes_but_nothing_else_on_settings(gateway, forwarded):
    paired(gateway)

    assert gateway.post("/api/settings", json={"autonomy_kill_switch": True}).status_code == 200
    assert json.loads(forwarded[-1]["body"]) == {"autonomy_kill_switch": True}
    count = len(forwarded)

    for body in (
        {"autonomy_kill_switch": False},
        {"autonomy_kill_switch": True, "risk_live_trading_enabled": True},
        {"autonomy_kill_switch": 1},
        {"risk_max_order_notional": 99999},
    ):
        assert gateway.post("/api/settings", json=body).status_code == 403
    assert gateway.post("/api/settings", content=b"not json", headers={"content-type": "application/json"}).status_code == 403
    assert len(forwarded) == count


def test_the_app_can_tell_it_is_on_a_paired_phone(gateway):
    assert gateway.get("/phone/session").status_code == 401
    paired(gateway)
    assert gateway.get("/phone/session").json() == {"phone": True, "read_only": True, "device": "My phone"}
