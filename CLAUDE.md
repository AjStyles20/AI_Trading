# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Astral AI Trading is a personal quant trading workstation: a React/TypeScript/Electron desktop client (`frontend/`) talking to a FastAPI backend (`backend/`) on `127.0.0.1:8000`, with shared domain logic in `core/` and SQLite persistence in `database/`. Paper trading is the default; live-capable broker adapters exist, but autonomous live trading is deliberately gated (see the maturity gates in `README.md`).

## Commands

Backend (run from the repo root; CI uses Python 3.12):

```bash
pip install -r backend/requirements.txt -r backend/requirements-test.txt
python backend/main.py                      # dev server on 127.0.0.1:8000
pytest backend/tests -q                     # full backend suite (what CI runs)
pytest backend/tests/test_risk_engine.py -q # one file
pytest backend/tests/test_trading_loop.py -k poll_delay -q   # one test
```

Frontend (from `frontend/`; CI uses Node 20; `--legacy-peer-deps` is required):

```bash
npm ci --legacy-peer-deps
npm run dev            # Vite renderer only (talks to backend at 127.0.0.1:8000)
npm run electron:dev   # Vite + Electron together
npm test               # vitest run + node --test electron/*.node.cjs
npx vitest run src/components/__tests__/StrategyBuilder.test.tsx   # one test file
npm run lint
npm run build          # tsc -b && vite build (CI runs this; type errors fail it)
```

Backend dependencies: `backend/requirements*.txt` are generated, hashed, universal (Linux + Windows) lock files for Python 3.12. Never edit them by hand. Edit `backend/requirements.in` (runtime), `requirements-test.in` or `requirements-build.in` (PyInstaller), then run `bash scripts/lock_backend.sh` and commit the `.in` file and the regenerated locks together. Pass `--upgrade-package <name>` to upgrade a single locked package. The CI `backend-locks` job fails when the locks are stale. It pins the uv version, so generate locally with that same version. Because the locks contain hashes, pip refuses any requirement without a hash. Never add an extra package on a pip command line next to `-r backend/requirements*.txt`; add it to a `.in` file instead.

Windows bundle (PowerShell, repo root): `scripts/build_windows_backend.ps1`, then `npm run electron:build` in `frontend/`. `scripts/smoke_windows_backend.ps1` and `scripts/smoke_windows_desktop.ps1` are what the `windows-desktop.yml` workflow uses to verify the bundle.

## Architecture

### Import conventions

There is no package config. Modules import as top-level packages from the repo root (`from core.risk_engine import ...`, `from database.sqlite_manager import ...`, `from backend.broker_integration.registry import ...`). Each `backend/*_api.py` adds the repo root to `sys.path`. `backend/main.py` also imports `ai_engine` and the routers *without* the `backend.` prefix, because it is run as a script from inside `backend/`. Tests import `backend.<module>`, so run pytest from the repo root.

### Backend layout

- `backend/main.py` creates the FastAPI app, includes one router per `*_api.py` (indicators, data, research, backtest, optimizer, strategy_store, validation, settings, trading) and defines the AI endpoints (`/api/chat`, `/api/strategy`, `/api/strategy/build`, `/api/ai/summary/*`).
- `backend/trading_api.py` is the largest module. It holds `LiveTradingManager` (the autonomous polling loop), `submit_guarded_order` (the **only** path any autonomous order may take), reconciliation, and recovery logic.
- `backend/broker_integration/`: `base.py` defines the `BrokerClient` ABC (capabilities, quote, validate, execute, order status, open orders, positions, cancel). Adapters cover paper, Binance, Bitget, and Alpaca, and `registry.py` resolves them. Broker-specific behaviour must stay inside an adapter. Autonomous readiness (`core/autonomy_readiness.py`) checks the adapter's declared capabilities.
- `backend/ai_engine/`: an LLM assistant and a strategy generator. The provider is OpenAI, Groq, or local Ollama, chosen explicitly in Settings. Never fall back silently to another provider. With no provider, AI endpoints return 503 or "unavailable", and the visual builder uses a local deterministic export.

### core/

`core/` holds pure domain logic that both the API layer and the tests use: market data (`data_service`), indicators, strategy execution (declarative via `declarative_strategy`, legacy Python via `safe_strategy_runtime`, dispatched by `strategy_execution`), backtesting, optimization/walk-forward, research evaluation, `risk_engine`, `position_ledger` (positions rebuilt from confirmed fills), `position_protection` (SL/TP), and `credential_provider` (OS keyring, with migration from legacy SQLite keys).

### Persistence

`database/sqlite_manager.py` owns the schema and handles migrations inline with `ALTER TABLE ... ADD COLUMN` guards. The DB lives at `$ASTRAL_DATA_DIR/astral.db`, or `database/astral.db` in a source checkout. Tests isolate the DB by monkeypatching `sqlite_manager.DB_PATH` to a tmp path. Follow that pattern so tests never touch the real DB.

### Desktop / packaging

In dev, the renderer calls `http://127.0.0.1:8000` directly (`frontend/src/lib/api.ts`). In production, Electron serves the build through the private `astral://app` protocol (`electron/protocol.cjs`) and forwards `/api/` to the backend. The packaged app starts its own PyInstaller backend (`backend/desktop_entry.py`) and passes it `ASTRAL_DATA_DIR` and `ASTRAL_DESKTOP_TOKEN`. When the token is set, the backend requires the `x-astral-desktop-token` header on `/api/*`. `electron/*.node.cjs` files hold Node-testable logic and are covered by `node --test`.

## Safety invariants (do not weaken)

This code places real orders, so it is intentionally fail-closed. `docs/SAFETY_BASELINE.md`, `docs/V5_SANDBOX_READINESS.md`, and `docs/ORDER_SUBMISSION_INCIDENT.md` are the authoritative specs. The key rules:

- **Guarded submission order:** re-read the persistent kill switch, then run central risk, broker validation and quantity normalization, risk again on the normalized quantity, persist the `submission_pending` intent with its client order ID, execute, and finally persist the cumulative fill.
- **Uncertain submissions:** a lost or invalid broker response leaves the intent unresolved, and that blocks further submissions. Never infer that an order was rejected.
- **Fills vs acceptance:** broker acceptance is not a fill. Positions come only from confirmed fills, and a broker/ledger position drift blocks trading.
- **Kill switch:** the autonomy kill switch defaults to armed. While armed, the loop only observes and reconciles, and creates no orders, including protective ones.
- **Price roles:** decisions use only completed candles. The broker quote is the execution reference, and the confirmed fill is the accounting truth.
- **Numeric inputs:** nonfinite numbers anywhere in the order path must be rejected.
- **API exposure:** the API stays loopback-only. Keep the `TrustedHostMiddleware`, origin, and fetch-metadata checks in `backend/main.py`, and never use wildcard CORS with credentials.
- **Legacy Python strategies:** the legacy Python strategy runtime is not an OS sandbox. Prefer the declarative strategy format, and never execute third-party Python strategies.
- **Credentials:** credentials belong in the OS credential store, not in SQLite.


## Rules
- Paper trading only. Never configure, read, or print real broker or AI API keys.
- Never disable or bypass the kill switch, risk checks, or order recovery logic.
- Don't start the live trading loop without asking me.
- Every bug fix needs a test. Run the relevant tests after every change.
- Ask before adding or upgrading dependencies.
- Work only on the claude-work branch. Never commit to master.
- Commit after each completed fix with a clear message.
- Never push, force-push, or rewrite history without asking me first.
