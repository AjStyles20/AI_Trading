# Astral AI Trading

Astral AI Trading is a personal, AI-assisted quantitative trading workstation built around a React/Electron desktop client, FastAPI backend, deterministic research tools, a broker-neutral execution layer, and fail-closed risk controls.

> **Current maturity:** research, backtesting, optimization, paper trading, and broker-sandbox readiness. Live-capable adapters exist, but meaningful-capital autonomous live deployment remains gated.

## Architecture

- **frontend/** — React + TypeScript + Electron desktop UI
- **backend/** — FastAPI APIs, AI assistant, broker adapters, trading runtime
- **core/** — market data, indicators, safe/declarative strategy execution, backtesting, optimization, research evaluation, risk, position ledger/protection, autonomy readiness
- **database/** — SQLite persistence for settings, trades, paper-account state and risk state
- **docs/** — safety, readiness and operating documentation
- **scripts/** — development and test utilities

The autonomous execution pipeline is:

```
completed market candle
        ↓
strategy / protection decision
        ↓
selected broker quote
        ↓
central risk + broker validation
        ↓
persistent kill-switch recheck
        ↓
broker submission
        ↓
order-status reconciliation
        ↓
confirmed fills
        ↓
persistent position ledger
        ↓
broker-position drift verification
```

A completed candle is an **observation/decision input**. The selected broker quote is the **execution reference**. The broker-confirmed fill is the **accounting truth**.

## Broker-neutral execution

Current adapters:

- Paper
- Binance
- Bitget
- Alpaca

Broker-specific behavior is isolated behind the common broker contract. Autonomous readiness requires market-order, quote, order-status, open-order and position capabilities. Missing order cancellation is surfaced as a warning rather than silently claimed.

Adding another broker or exchange does not require changing the product architecture, but the adapter must provide the required lifecycle and pricing capabilities before autonomous readiness can pass.

## Safety model

Paper trading remains the default.

The runtime includes:

- central pre-trade risk checks;
- live-trading opt-in;
- maximum order notional and position sizing limits;
- daily-loss and drawdown controls;
- persistent autonomy kill switch, default armed;
- fail-closed startup recovery verification;
- full scoped trade reconciliation before strategy execution;
- durable order intent and client-ID recovery after uncertain submissions;
- unresolved-order blocking;
- confirmed-fill position reconstruction;
- broker/ledger position-drift blocking;
- completed-candle decision boundaries;
- broker-specific execution references;
- monotonic cumulative-fill reconciliation;
- stop-loss / take-profit position protection;
- no-pyramiding long-position semantics;
- persistent paper-account state;
- OS credential-store integration with legacy SQLite migration support.

When the kill switch is armed, the autonomous loop remains alive only to observe and reconcile broker state. It does **not** create protective, strategy or liquidation orders automatically.

## Strategy execution

The preferred strategy format is declarative. Legacy Python strategies use the restricted in-process runtime and are treated as trusted/application-generated code only.

The restricted Python runtime is **not an operating-system sandbox**. Do not execute arbitrary third-party Python strategies.

## Research and backtesting

Astral includes:

- deterministic backtesting;
- fees/slippage handling;
- next-bar risk-exit semantics;
- terminal liquidation;
- out-of-sample evaluation;
- rolling fixed-strategy OOS evaluation;
- walk-forward parameter selection using past-only data;
- research scoring and evidence warnings;
- strategy optimization and validation.

No backtest, optimizer score or AI output establishes future profitability.

AI chat, strategy generation, summaries and AI graph export can use OpenAI,
Groq or a locally running Ollama model. In Settings, choose the provider and
optionally enter a model ID. OpenAI uses its API key (default model
`gpt-4.1-mini`); Groq uses its own API key (default `openai/gpt-oss-20b`);
Ollama needs no API key, but must be running on this computer at
`127.0.0.1:11434` with the selected model already installed. The Ollama
model name is required. Groq's free tier has usage limits and provider
availability/pricing can change. Local model speed and memory needs depend
on the chosen model and computer; no hardware requirement is assumed.

The selected provider is used explicitly; Astral does not silently send
prompts to another provider. Without a configured provider, AI endpoints
report that AI is unavailable; the visual builder can still export a local
deterministic draft. Backtesting and paper trading work without any AI key.

For Groq, obtain your own key from its [console](https://console.groq.com/keys),
choose Groq in Settings, enter the key and save. For Ollama, [install
Ollama](https://docs.ollama.com/quickstart), pull a model suitable for your
computer with `ollama pull <model-name>`, choose Ollama in Settings, enter
the same model name and save. Ollama runs separately; the installer does not
include a model or start its server. OpenAI and Groq prompts leave your
computer for their respective providers; Ollama prompts go to localhost.

## Development

Backend:

```bash
pip install -r backend/requirements.txt -r backend/requirements-test.txt
python backend/main.py
```

Frontend:

```bash
cd frontend
npm ci --legacy-peer-deps
npm run dev
```

For the Electron desktop client and Windows bundle instructions, see [frontend/README.md](frontend/README.md). Source development runs the backend separately; the Windows bundle includes it.

Tests:

```bash
pytest backend/tests -q
cd frontend
npm test
npm run build
```

GitHub Actions runs both backend and frontend validation on pushes and pull requests.

## Maturity gates

- **V0 — AI-assisted strategy workstation:** completed
- **V1 — safe strategy research platform:** completed
- **V2 — reproducible quantitative research engine:** substantially completed
- **V3 — AI analyst / regime-aware research:** partial
- **V4 — portfolio/risk-aware paper trader:** substantially completed
- **V5 — broker sandbox readiness:** current hardening milestone
- **V6 — controlled small-capital live pilot:** gated
- **V7 — continually evaluated adaptive trading agent:** future

Real-money autonomous deployment requires explicit review after broker sandbox testing, operational incident procedures, extended soak evidence and hard capital limits.

See `docs/V5_SANDBOX_READINESS.md`, `docs/ORDER_SUBMISSION_INCIDENT.md`
and `docs/SAFETY_BASELINE.md`.

## Important limitations

Astral is engineering and research software, not evidence that a strategy is profitable. Market data, broker APIs, execution latency, spread, fees, liquidity, outages and strategy overfitting can all materially alter results. AI-generated ideas should be treated as hypotheses to test rather than trading instructions.
