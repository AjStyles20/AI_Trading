from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app, base_url="http://127.0.0.1:8000")


def test_cross_site_forms_cannot_reach_trading_or_settings_handlers():
    for endpoint in ("/api/trading/toggle", "/api/settings"):
        response = client.post(endpoint, headers={"Origin": "https://example.invalid"})
        assert response.status_code == 403
        assert response.json()["detail"] == "Untrusted request origin"

    assert client.post("/api/settings", headers={"Origin": "null"}).status_code == 403
    assert client.post("/api/settings", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/api/settings", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403


def test_local_clients_and_dev_preflight_remain_available():
    assert client.get("/health").status_code == 200
    assert client.post("/api/settings", headers={"Origin": "http://localhost:5173"}).status_code != 403
    assert client.post("/api/settings").status_code != 403
    preflight = client.options(
        "/api/settings",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_dns_rebinding_host_is_rejected():
    response = client.get("/api/settings", headers={"Host": "attacker.invalid:8000"})
    assert response.status_code == 400
