# Astral AI Safety and Research Baseline

## Repository baseline

The initial repository commit was `05ee280b24edb537c841962564cf9198022000ec`.

The original system already included market-data retrieval, AI-assisted strategy generation, validation, backtesting, optimization, persistent storage, paper trading and live-capable broker adapters. The hardening work since that baseline has focused on making research and execution behavior explicit, testable and fail-closed.

## Current safety boundaries

### Strategy runtime

Astral supports a declarative strategy format and a restricted legacy-Python runtime. The Python runtime performs AST validation and restricted builtins, but it remains an in-process Python execution mechanism.

Therefore:

- application-generated/trusted Python strategies are supported;
- arbitrary third-party Python strategies are not considered safe;
- the restricted runtime is not an OS-level sandbox.

### Order authority

Every autonomous order must pass the shared guarded submission path:

1. re-read the persistent autonomy kill switch;
2. central risk evaluation;
3. broker validation and quantity normalization;
4. broker execution;
5. persistence of requested quantity and confirmed cumulative fill state.

Broker acceptance is not treated as a fill.

Numerical inputs in the order path must be finite. The risk engine rejects
nonfinite quantity, price, notional, configured limits and supplied equity or
position state. Broker quote references reject nonfinite prices. After broker
quantity normalization, central risk runs again on the actual quantity before
submission; an upward rounding cannot bypass the order or position limit.

### Price semantics

Astral separates:

- **decision observation:** latest completed candle;
- **execution reference:** selected broker quote;
- **actual execution/accounting:** broker-confirmed fill.

Protective exits and ordinary strategy orders use the broker quote contract. Paper simulation accepts an explicitly supplied completed-candle reference and labels that provenance; it does not pretend to be exchange quote data.

### Order lifecycle and reconciliation

The autonomous loop reconciles the full active trading scope every poll before strategy evaluation.

Safety invariants include:

- unresolved prior orders block overlapping autonomous orders;
- cumulative filled quantity may never regress;
- reconciliation failure keeps the order unresolved;
- completed SELL transitions are emitted once;
- confirmed positions are reconstructed from cumulative fills;
- broker position quantity is compared against the reconstructed ledger;
- nonfinite or negative broker/ledger position quantities fail readiness;
- material drift blocks autonomous execution.

### Startup and restart recovery

Direct runtime start defaults to `recovery_verified=False`.

The normal API start path marks recovery verified only after the readiness builder has:

- loaded the full scoped trade history;
- reconciled unresolved broker orders;
- reconstructed the confirmed-fill position;
- retrieved broker account/position state;
- rejected unresolved lifecycle state;
- rejected broker/ledger quantity drift;
- verified broker capability declarations.

A restarted process therefore does not inherit previous runtime authorization.

### Persistent autonomy kill switch

`autonomy_kill_switch` is stored in SQLite and defaults to **armed** on both new and migrated databases.

When armed:

- startup is rejected;
- guarded submission rejects new autonomous orders;
- an already-running loop continues market/broker observation and reconciliation;
- strategy and protection evaluation are skipped;
- no automatic liquidation is fabricated.

This is an emergency pause, not an automatic flatten-position instruction.

### Broker capability readiness

Required autonomous capabilities are:

- market orders;
- quotes;
- order status;
- open orders;
- positions.

Cancellation is currently a warning rather than a universal hard gate because broker support differs. This limitation must remain visible in sandbox certification.

### Credentials

Credential precedence is:

1. environment variable;
2. OS credential store;
3. legacy SQLite value during migration compatibility.

New plaintext credential writes to SQLite are rejected. Legacy credentials can be explicitly migrated to the secure store and are deleted from SQLite only after successful write-and-readback verification.

## Research integrity

Backtests and optimization are research evidence, not profitability claims.

Current controls include deterministic accounting, fees/slippage, delayed risk exits, terminal liquidation, out-of-sample evaluation, rolling evaluation and walk-forward parameter selection. Remaining statistical and market-realism limitations must be considered before capital allocation.

## Development gates

- **Gate A — deterministic research**
- **Gate B — safe strategy representation/runtime**
- **Gate C — trustworthy backtesting and OOS evidence**
- **Gate D — realistic paper trading and persistent risk controls**
- **Gate E — broker sandbox operational readiness**
- **Gate F — controlled small-capital live pilot**
- **Gate G — continually evaluated adaptive operation**

Passing a software gate means the implementation and tests satisfy the stated engineering controls. It does not imply strategy profitability or eliminate market/broker risk.

## Current deployment classification

Appropriate now:

- local research;
- strategy development;
- backtesting and optimization;
- paper trading;
- broker sandbox/test-environment validation.

Still gated:

- arbitrary third-party Python strategy execution;
- meaningful-capital autonomous live trading;
- unattended production deployment;
- any claim of expected profitability.

See `docs/V5_SANDBOX_READINESS.md` for the current operational-readiness checklist.
