# Uncertain Order Submission: Operator Procedure

Astral writes a `submission_pending` trade row and a unique `client_order_id`
before it calls a broker. The database commits that row before network I/O.
The same-scope admission check is transactional, so a second autonomous order
for that symbol, broker and execution mode cannot be submitted while an order
is unresolved. The client ID is passed to Binance (`newClientOrderId`),
Bitget (`clientOid`) and Alpaca (`client_order_id`).

## When this procedure applies

- Broker request timed out, connection dropped or response could not be parsed.
- The process stopped after the broker call but before its result was saved.
- Broker returned a malformed fill or Astral could not persist the result.
- Trade History shows `submission_pending`.

The outcome is **unknown**, including when a request raised an exception. Do
not infer that the broker rejected it or resubmit the strategy order.

## Recovery steps

1. Keep autonomy paused (arm the persistent kill switch if the process is
   running). Inspect the Trade History row's symbol, broker, mode, timestamp and
   client order ID. Do not disclose API credentials or full account details.
2. Use **Refresh Status**. For a live-mode row, Astral queries the owning
   broker by broker order ID when known, otherwise by client order ID. A valid
   broker response is reconciled into the same trade row; confirmed fills then
   enter the ledger. Repeated refreshes never resubmit the order.
3. If lookup fails or returns no order, inspect the broker's order and fill
   history and account position directly. A momentary “not found” or unavailable
   API is not proof that the order never arrived. Compare the client ID and
   symbol, requested quantity, side, execution environment and time window.
4. If the order exists, restore connectivity and refresh until the actual
   cumulative fills and final status are recorded. Investigate any broker vs
   ledger position drift before disarming the kill switch.
5. If no order can be found, preserve the incident row and evidence. Clearing
   an uncertain intent requires a reviewed operator recovery procedure; this
   release deliberately has no button that treats “not found” as rejection.

For simulated Paper execution, a crash can occur after the account snapshot
was saved but before the trade result was saved. The paper adapter does not
have exchange order history. Compare the persisted account snapshot and
confirmed-fill ledger; do not automatically clear the intent.

## Implementation and evidence boundary

This release proves the local durable-intent and restart behavior in
deterministic tests. Adapter tests verify request and lookup field mappings.
It does **not** prove that a particular broker sandbox accepted, indexed and
returned a client ID through a real network session. Each venue needs a
documented sandbox incident exercise before unattended operation.

Official endpoint references:

- [Binance Spot new order and query order](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/trade)
- [Alpaca order lookup by client ID](https://docs.alpaca.markets/us/reference/getorderbyclientorderid)
- [Bitget Classic Spot order info](https://www.bitget.com/docs/catalog/classic-spot-trade/classic-spot-trade)

Live capital remains gated. Broker client IDs are correlation keys for
recovery, not a license to retry a submission: a venue may permit reuse of an
ID after a prior order reaches a terminal state.
