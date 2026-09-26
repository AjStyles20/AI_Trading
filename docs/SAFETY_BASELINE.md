# Safety and Research Baseline

## Baseline

The initial repository commit is `05ee280b24edb537c841962564cf9198022000ec`. The code already contains market-data retrieval, AI-assisted strategy generation, strategy validation, backtesting, optimization, persistent storage, paper trading, and live-capable broker adapters.

## Critical findings

### 1. Arbitrary strategy execution

`core/trading_engine.py`, `core/strategy_validator.py`, and the optimizer execute Python strategy code with `exec()`. Passing empty globals does **not** make Python safe. Strategy code must therefore be treated as trusted-only until a restricted strategy representation or hardened sandbox is introduced.

### 2. Execution outran risk controls

The trading loop can construct and submit broker orders. Before this hardening phase, there was no single pre-trade risk authority between a signal and broker execution.

The new `core/risk_engine.py` begins that boundary. It intentionally defaults to conservative limits and locks live execution unless explicitly enabled.

### 3. Backtest confidence is not yet sufficient for capital allocation

The current backtester models basic fees and slippage and computes return, drawdown, win rate, and buy-and-hold return. It still needs explicit execution-timing rules, stronger accounting tests, bias/leakage tests, richer risk metrics, and out-of-sample/walk-forward evaluation.

### 4. Optimization can overfit

The optimizer searches parameter grids and ranks them on the same backtest sample. Its score is useful for experimentation, not evidence of future performance. Train/validation/test separation and walk-forward evaluation are required.

### 5. Live data and execution need stronger failure semantics

Market-data functions currently fail to empty DataFrames in several cases. That is useful for UI resilience, but trading execution should distinguish stale data, provider failure, invalid symbols, and genuinely empty markets and should fail closed.

## Development gates

- **Gate A — deterministic research:** reproducible datasets, strategies, costs and metrics.
- **Gate B — safe strategy runtime:** generated strategies cannot execute arbitrary host operations.
- **Gate C — trustworthy backtests:** bias tests, execution timing, accounting and out-of-sample validation.
- **Gate D — realistic paper trading:** portfolio cash, positions, fills, rejects, reconciliation and risk limits.
- **Gate E — broker sandbox:** exchange/broker test environments with no meaningful capital.
- **Gate F — controlled live pilot:** only after explicit review, hard limits and a kill switch.

Until Gates A-E are satisfied, live trading should remain disabled.


## Credential and broker-environment hardening

Credential storage and broker environment selection are separate concerns.

- New credentials are written to the operating-system credential store through `core/credential_provider.py`.
- Environment variables remain the highest-precedence runtime credential source.
- Legacy SQLite credentials remain readable only for backward compatibility; new plaintext writes are rejected.
- `POST /api/settings/migrate-credentials` performs an explicit legacy migration. Each legacy secret is written to the OS store and read back for exact verification before its SQLite copy is eligible for deletion.
- A secure-store write or verification failure fails closed and leaves the legacy SQLite copy intact.
- Credential-presence reporting exposes booleans only, never secret values.
- Binance `live/testnet` and Bitget `live/demo` selections are ordinary settings, not credentials. Existing `binance_testnet` and `bitget_demo` legacy flags are migrated into dedicated settings columns and removed from the legacy credential object.
- The frontend changes broker environments by posting only the relevant environment field; it no longer round-trips the credential dictionary.

### Credential resolution order

1. Environment variable.
2. OS credential store.
3. Legacy SQLite value during migration compatibility.

### Migration invariant

A legacy secret must never be deleted merely because another credential source exists. Deletion is permitted only after the OS credential-store write has succeeded and the stored value has been read back and verified.

### Validation status

The credential/environment hardening slice is covered by database persistence, migration, cleanup, secure-store failure, presence-reporting, API, frontend test, TypeScript-build, and production-build checks. CI run #274 passed both backend and frontend jobs.
