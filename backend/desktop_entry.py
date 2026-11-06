"""Entry point for the Windows backend bundle; data and token come from Electron."""

import os
import sys

if getattr(sys, "frozen", False) and not os.environ.get("ASTRAL_DATA_DIR"):
    raise SystemExit("ASTRAL_DATA_DIR is required for the packaged backend")
if getattr(sys, "frozen", False) and not os.environ.get("ASTRAL_DESKTOP_TOKEN"):
    raise SystemExit("ASTRAL_DESKTOP_TOKEN is required for the packaged backend")

# The same bundle also runs the read-only phone gateway when Electron starts it
# with --phone-gateway; it never serves the trading API itself.
if "--phone-gateway" in sys.argv:
    from backend.phone_gateway import main as run_phone_gateway

    if __name__ == "__main__":
        run_phone_gateway([arg for arg in sys.argv[1:] if arg != "--phone-gateway"])
else:
    from backend.main import app  # noqa: E402
    import uvicorn  # noqa: E402

    if __name__ == "__main__":
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
