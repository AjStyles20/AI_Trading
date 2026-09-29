"""Entry point for the Windows backend bundle; data and token come from Electron."""

import os
import sys

if getattr(sys, "frozen", False) and not os.environ.get("ASTRAL_DATA_DIR"):
    raise SystemExit("ASTRAL_DATA_DIR is required for the packaged backend")
if getattr(sys, "frozen", False) and not os.environ.get("ASTRAL_DESKTOP_TOKEN"):
    raise SystemExit("ASTRAL_DESKTOP_TOKEN is required for the packaged backend")

from backend.main import app  # noqa: E402
import uvicorn  # noqa: E402


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
