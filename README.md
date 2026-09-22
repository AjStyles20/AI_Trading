# Astral AI Trading

Astral AI Trading is a personal, AI-assisted quantitative trading workstation. It combines a React/Electron desktop interface with a FastAPI backend for market data, strategy generation, validation, backtesting, optimization, paper trading, and broker integrations.

> **Current maturity:** research / paper-trading software. Live broker adapters exist, but live execution must not be treated as production-ready.

## Architecture

- **frontend/** — React + TypeScript + Electron desktop UI
- **backend/** — FastAPI API, AI assistant, strategy APIs, broker adapters
- **core/** — market data, indicators, validation, backtesting, optimization, trading and risk logic
- **database/** — SQLite persistence and vector storage
- **scripts/** — development and API test utilities

The intended execution pipeline is:

```
Market data -> Strategy -> Validation -> Signal -> Risk engine
            -> Broker validation -> Paper/live execution -> Trade journal
```

## Safety model

Paper trading is the default. The central risk engine rejects invalid orders, enforces a maximum order notional, and keeps live trading locked unless it is explicitly enabled in settings. Broker-side validation remains mandatory after risk approval.

Generated strategy code is currently Python and is therefore considered **untrusted**. The existing validator checks strategy output shape, but Python execution is not yet sandboxed. Do not run strategy code from untrusted third parties.

## Development

Backend dependencies are in `backend/requirements.txt`. Frontend dependencies and scripts are in `frontend/package.json`.

Typical backend startup:

```bash
pip install -r backend/requirements.txt
python backend/main.py
```

Typical frontend startup:

```bash
cd frontend
npm install
npm run dev
```

Run backend tests with:

```bash
pytest backend/tests
```

## Roadmap

1. Establish deterministic tests and CI.
2. Put all execution paths behind the central risk engine.
3. Replace arbitrary generated-Python execution with a restricted strategy representation or hardened sandbox.
4. Strengthen the backtester: execution timing, fees/slippage, risk exits, benchmark metrics, and bias tests.
5. Add walk-forward/out-of-sample evaluation and experiment persistence.
6. Improve paper-account realism and reconciliation.
7. Permit controlled live execution only after the preceding gates pass.

## Important limitations

This software does not establish that any strategy is profitable. Backtest and optimization output can be misleading if affected by overfitting, look-ahead bias, survivorship bias, poor data, or unrealistic execution assumptions. Treat AI-generated trading ideas as hypotheses to test, not trading instructions.
