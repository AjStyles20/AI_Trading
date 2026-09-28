# V5 Broker Sandbox Readiness

## Purpose

V5 establishes the engineering controls required before Astral can be exercised autonomously against broker/exchange sandbox or test environments. It does **not** authorize meaningful-capital live trading.

## Entry conditions

An autonomous session may start only when:

- the persistent kill switch is explicitly disarmed;
- the broker is configured for the requested environment;
- the account is trade-enabled;
- the requested asset type is supported;
- required broker lifecycle capabilities are declared;
- a broker quote path is available;
- scoped order history has been reconciled;
- no unresolved prior order remains;
- reconstructed ledger quantity agrees with broker position quantity;
- startup recovery has been verified.

Live mode additionally remains behind the explicit central-risk live-trading opt-in.

## Required broker capabilities

A V5-capable adapter must support:

- market order submission;
- broker/venue quote retrieval;
- order-status refresh;
- open-order inspection;
- position inspection.

Cancellation support is strongly preferred and currently produces a readiness warning when absent.

Current adapters:

| Adapter | Assets | Environment support | Quote source |
| --- | --- | --- | --- |
| Paper | crypto/stock simulation | paper | explicit completed-candle simulation reference / persisted simulated mark |
| Binance | crypto | testnet/live | Binance book ticker |
| Bitget | crypto | demo/live | Bitget spot ticker |
| Alpaca | stock | paper/live | Alpaca latest stock quote |

## Runtime invariants

The autonomous loop performs the following order of work:

1. fetch and validate market data;
2. restrict decisions to completed candles;
3. load and reconcile full scoped trade history;
4. reconstruct the confirmed-fill position;
5. reject unverified startup recovery;
6. honor the persistent kill switch;
7. evaluate protection for an existing position;
8. obtain a broker quote for any order attempt;
9. compare broker and ledger quantities;
10. pass guarded risk/broker validation;
11. submit;
12. persist requested and confirmed fill state;
13. reconcile asynchronously on subsequent polls.

A failed protective-exit attempt ends that poll. Ordinary strategy evaluation cannot bypass a protection path that failed because of quote, drift or validation errors.

## Kill-switch semantics

The kill switch is a **zero new autonomous order generation** control.

When armed during a running session:

- reconciliation continues;
- strategy evaluation stops;
- protective-order generation stops;
- new order construction/submission stops;
- no automatic liquidation order is created.

Manual broker inspection/cancellation remains an operator responsibility.

## Restart semantics

Runtime authorization is not persisted.

After restart, `recovery_verified` starts false. The API performs a fresh readiness/reconciliation pass before starting the trading loop with recovery authorization.

Unresolved partial fills and position drift both block restart authorization.

## Incident and soak coverage

The deterministic V5 test matrix includes:

- repeated same-candle polling;
- order partial fills;
- transient broker status outage;
- broker recovery after outage;
- cumulative-fill monotonicity;
- rejection of regressive broker fill reports;
- exactly-once completed SELL transition;
- unresolved-order blocking;
- position drift;
- quote failure during protection;
- no strategy fall-through after failed protection;
- mid-session kill-switch activation;
- reconcile-only operation while paused;
- restart with unresolved partial fills;
- persistent kill-switch migration, disarm and re-arm;
- broker quote side semantics;
- broker-specific quote mapping;
- Paper simulation quote provenance;
- normal strategy order using broker execution quote rather than candle close.
- durable submission intent before network I/O, client-ID lookup and
  no-duplicate blocking after an uncertain outcome.

See `docs/ORDER_SUBMISSION_INCIDENT.md` for the operator procedure and the
remaining broker-specific evidence requirement.

## Release gate for this phase

V5 code may be merged only after:

- backend pytest suite passes;
- frontend test suite passes;
- frontend production build passes;
- safety documentation reflects actual runtime behavior;
- no meaningful-capital live deployment is enabled as part of the merge.

## What V5 does not prove

V5 does not prove:

- profitability;
- broker uptime;
- exchange fairness or liquidity;
- production readiness for unattended capital;
- correctness of every broker-specific edge case;
- safety of arbitrary third-party Python strategy code.

## Next gate: V6

V6, if pursued, is a separately approved controlled-live pilot. It should require:

- extended sandbox soak history;
- broker-specific test-environment evidence;
- explicit incident/runbook procedures;
- capital-at-risk limits materially below account capacity;
- operator review of live credentials and permissions;
- staged deployment with auditable stop criteria.

No V6 capital deployment is authorized by this document.
