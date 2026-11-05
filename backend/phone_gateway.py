"""Read-only phone gateway: lets a paired phone use Astral over a private network.

This is a separate process in front of the backend. The backend itself stays
loopback-only. The gateway:

- listens only on a Tailscale address (100.64.0.0/10) or this computer, never on
  0.0.0.0 or a home network;
- requires a per-device token (created and revoked in the desktop's Settings);
- forwards only an allowlist of read-only requests, plus arming the kill switch;
- serves the built web app so the phone can use the normal interface.

Traffic inside Tailscale is end-to-end encrypted by WireGuard, so the gateway
speaks plain HTTP within it. Run it with:

    python backend/phone_gateway.py --host 100.x.y.z

See docs/MOBILE_ACCESS.md.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import urllib.error
import urllib.request

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.sqlite_manager import verify_phone_token  # noqa: E402

BACKEND = "http://127.0.0.1:8000"
DEFAULT_PORT = 8765
COOKIE = "astral_phone"
TAILSCALE_NETWORK = ipaddress.ip_network("100.64.0.0/10")
MAX_BODY_BYTES = 64 * 1024
DIST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")

# (method, path pattern) pairs a phone may reach. Everything else is refused.
# Nothing here can place, change or cancel an order, change settings, disarm,
# start a session, or call the AI provider (which costs money).
ALLOWED = [
    ("GET", r"/api/settings"),
    ("GET", r"/api/market/(quote|price)/(stock|crypto)/[^/]{1,40}"),
    ("POST", r"/api/market/history"),
    ("GET", r"/api/trading/(status|journal|positions|open-orders|history|brokers)"),
    ("GET", r"/api/trading/account/[a-z_]{1,20}"),
    ("GET", r"/api/alerts"),
    ("GET", r"/api/chat/history"),
]
FORWARDED_HEADERS = {"content-type", "accept"}

READ_ONLY_DETAIL = "Not available from a phone: phone access is read-only."


def check_bind_address(host: str) -> str:
    """Refuse any address other than a Tailscale one or this computer."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError(f"{host!r} is not an IP address. Use your Tailscale address (100.x.y.z).") from exc
    if address.is_loopback or (address.version == 4 and address in TAILSCALE_NETWORK):
        return host
    raise ValueError(
        f"Refusing to listen on {host}: the phone gateway only listens on a Tailscale address "
        "(100.64.0.0/10) or this computer, never on a home network or all interfaces."
    )


def is_allowed(method: str, path: str) -> bool:
    return any(method == allowed_method and re.fullmatch(pattern, path) for allowed_method, pattern in ALLOWED)


def _is_arm_request(method: str, path: str, body: bytes | None) -> bool:
    """The app arms the kill switch with POST /api/settings. That is allowed only
    when the body is exactly {"autonomy_kill_switch": true}; any other settings
    change, including disarming, is refused."""
    if method != "POST" or path != "/api/settings" or not body:
        return False
    try:
        parsed = json.loads(body)
    except ValueError:
        return False
    # `is True`, not ==: in Python 1 == True, and only a real true is accepted.
    return isinstance(parsed, dict) and list(parsed) == ["autonomy_kill_switch"] and parsed["autonomy_kill_switch"] is True


def _forward(method: str, path_and_query: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes, str]:
    request = urllib.request.Request(f"{BACKEND}{path_and_query}", data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read(), response.headers.get("content-type", "application/json")
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers.get("content-type", "application/json")
    except (urllib.error.URLError, TimeoutError, OSError):
        return 503, json.dumps({"detail": "The desktop backend is not reachable. Is Astral running?"}).encode(), "application/json"


PAIR_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Pair with Astral</title></head>
<body style="font-family:sans-serif;background:#0a0a0c;color:#ddd;padding:24px">
<p id="msg">Pairing...</p>
<script>
// The token is in the URL fragment, which browsers never send to a server.
const token = location.hash.slice(1);
history.replaceState(null, '', '/pair');
fetch('/pair', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({token})})
  .then(r => { if (r.ok) location.replace('/'); else document.getElementById('msg').textContent =
    'This pairing link is not valid or was revoked. Create a new one in Astral on your computer.'; });
</script></body></html>"""


def create_gateway_app(forward=_forward, dist_dir: str = DIST_DIR, desktop_token: str | None = None) -> Starlette:
    desktop_token = desktop_token if desktop_token is not None else os.environ.get("ASTRAL_DESKTOP_TOKEN")

    def device_for(request: Request):
        return verify_phone_token(request.cookies.get(COOKIE))

    async def pair_page(request: Request):
        if request.method == "GET":
            return HTMLResponse(PAIR_PAGE)
        try:
            token = (await request.json()).get("token")
        except Exception:
            token = None
        if not isinstance(token, str) or verify_phone_token(token) is None:
            return JSONResponse({"detail": "Invalid or revoked pairing token."}, status_code=401)
        response = JSONResponse({"status": "paired"})
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", max_age=60 * 60 * 24 * 365)
        return response

    async def arm(request: Request):
        if device_for(request) is None:
            return JSONResponse({"detail": "This phone is not paired."}, status_code=401)
        status, body, content_type = await run_in_threadpool(
            forward, "POST", "/api/settings", _backend_headers({"content-type": "application/json"}),
            json.dumps({"autonomy_kill_switch": True}).encode(),
        )
        return Response(body, status_code=status, media_type=content_type)

    def _backend_headers(incoming: dict[str, str]) -> dict[str, str]:
        # Only plain content headers go through: no cookies, origin or fetch
        # metadata from the phone, and the phone's token never reaches the backend.
        headers = {k: v for k, v in incoming.items() if k.lower() in FORWARDED_HEADERS}
        if desktop_token:
            headers["x-astral-desktop-token"] = desktop_token
        return headers

    async def api(request: Request):
        if device_for(request) is None:
            return JSONResponse({"detail": "This phone is not paired."}, status_code=401)
        path = request.url.path
        body = await request.body() if request.method == "POST" else None
        if body is not None and len(body) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Request too large."}, status_code=413)
        if not (is_allowed(request.method, path) or _is_arm_request(request.method, path, body)):
            return JSONResponse({"detail": READ_ONLY_DETAIL}, status_code=403)
        query = f"?{request.url.query}" if request.url.query else ""
        status, payload, content_type = await run_in_threadpool(
            forward, request.method, path + query, _backend_headers(dict(request.headers)), body,
        )
        return Response(payload, status_code=status, media_type=content_type)

    async def app_files(request: Request):
        if device_for(request) is None:
            return RedirectResponse("/pair", status_code=302) if request.url.path == "/" else \
                JSONResponse({"detail": "This phone is not paired."}, status_code=401)
        relative = request.url.path.lstrip("/") or "index.html"
        root = os.path.realpath(dist_dir)
        target = os.path.realpath(os.path.join(root, relative))
        if not target.startswith(root + os.sep) or not os.path.isfile(target):
            target = os.path.join(root, "index.html")
        if not os.path.isfile(target):
            return JSONResponse({"detail": "The web app is not built. Run npm run build in frontend/."}, status_code=503)
        return FileResponse(target)

    routes = [
        Route("/pair", pair_page, methods=["GET", "POST"]),
        Route("/phone/arm", arm, methods=["POST"]),
        Route("/api/{rest:path}", api, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
        Route("/{rest:path}", app_files, methods=["GET"]),
    ]
    return Starlette(routes=routes)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Read-only phone gateway for Astral AI.")
    parser.add_argument("--host", required=True, help="Your computer's Tailscale address (100.x.y.z).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    host = check_bind_address(args.host)
    import uvicorn
    print(f"Phone gateway on http://{host}:{args.port} (read-only; pair phones in Astral's Settings).")
    uvicorn.run(create_gateway_app(), host=host, port=args.port)


if __name__ == "__main__":
    main()
