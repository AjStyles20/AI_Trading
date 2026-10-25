# Astral AI: product vision and roadmap

This is the plan for taking Astral from a personal research workstation to a
complete, secure trading companion that runs on any device. It is used by one
person today and is being built so that others can use it later.

Work happens in small, tested, committed steps. Each phase ends with a working
product, not a half-built one.

---

## 1. Vision

Astral is a **trading companion**. It does not replace the trader:

- **You see** markets live on any device: desktop, laptop, phone or tablet.
- **You research** with charts, indicators, backtests and walk-forward
  evaluation.
- **You practise** on demo accounts (paper trading and broker sandboxes).
- **You trade** on real accounts, but only when you choose to and only within
  limits you set.
- **You talk with your AI** by text or voice. It sees what you see, learns your
  preferences, asks questions, shares ideas and challenges weak reasoning.
- **You capture and discuss**: screenshots, screen recordings and chart
  snapshots that the AI can look at with you.

## 2. The guiding principle: the user is the orchestrator

Every feature follows these rules. They are not optional and are never traded
away for convenience.

1. **The AI proposes; the user decides.** The AI can analyse, explain, suggest,
   question and draft. It can never place, change or cancel an order, move
   money, or change risk settings by itself.
2. **Every action that touches money needs an explicit human confirmation**,
   and every order goes through the single guarded submission path with its risk
   checks and kill switch (see `docs/SAFETY_BASELINE.md`).
3. **Demo is the default.** Real accounts must be switched on deliberately,
   are always visually distinct, and carry hard limits.
4. **Automation stays on a leash.** Autonomous strategies run only within limits
   the user set, can be stopped instantly with the kill switch, and keep a full
   audit trail.
5. **Nothing happens silently.** Every AI suggestion, every automated decision
   and every order is logged and can be reviewed.
6. **Privacy by default.** The user chooses what the AI and any cloud service
   can see; screen capture, voice and memory are opt-in.

---

## 3. Phases

| # | Phase | Outcome |
|---|---|---|
| 0 | **Baseline** | Current work pushed; Windows installer built and verified in CI |
| 1 | **Core experience** | A polished desktop app for charts and research |
| 2 | **AI companion** | An AI that sees your data, remembers, asks and suggests |
| 3 | **Complete paper trading** | Positions, profit and loss, history and alerts, all on demo money |
| 4 | **Security and release quality** | Hardened, signed, documented, and ready for other users |
| 5 | **Demo broker accounts** | Real broker APIs in their sandbox/testnet environments |
| 6 | **Voice, screenshots and recording** | Talk to the AI; capture and discuss what is on screen |
| 7 | **Any device** | A secure phone and tablet companion |
| 8 | **Real accounts** | Real-money trading under strict, user-set limits, after review |
| 9 | **Multi-user product** | Accounts, onboarding, licensing and support for other people |

The order matters: each phase builds the foundation the next one needs. Voice
and mobile come after security hardening because both open new ways in. Real
money comes after demo accounts have proven the order path.

### Phase 0: Baseline
- Push `claude-work`; open a pull request so the Windows desktop workflow builds
  and smoke-tests the installer with the live Binance stream.
- Decide what to do with the untracked `scratch/` folder.

### Phase 1: Core experience
- RSI, MACD and ATR in their own panels below the price chart.
- Live prices and daily change in the watchlist; working symbol search; add and
  remove watchlist symbols.
- An honest sentiment badge ("needs AI" when no provider is set).
- Consistent loading, empty and error states; keyboard shortcuts.
- Persist user preferences (timeframe, indicators, layout).

### Phase 2: AI companion
- **Sees your data:** every question carries the current symbol, live price,
  timeframe, indicator values, open positions and recent backtests.
- **Remembers:** preferences, past decisions and lessons, in local memory the
  user can view, edit and delete.
- **Asks questions:** clarifies vague requests before generating strategies, and
  checks the user's goals and risk tolerance.
- **Shares ideas:** suggests strategies to test, flags risks and overfitting,
  and summarises what changed in the market, always labelled as suggestions.
- **Builder export** includes each node's settings.
- **Proposals, not actions:** the AI can draft "run this backtest" or "paper
  trade this", shown as cards the user approves or rejects.

### Phase 3: Complete paper trading
- Positions and live profit and loss, trade history, and an equity curve.
- A dashboard of running strategies with start, stop and kill-switch controls.
- Price and indicator alerts with desktop notifications.
- Session journal: what ran, what it did, and why.

### Phase 4: Security and release quality
- A threat model document, and a security review of every entry point.
- Electron hardening: a content security policy, and a strict allowlist for
  external connections.
- Dependency hygiene: resolve the npm audit findings and keep everything pinned
  and locked.
- An audit log for settings changes, AI proposals and every order.
- Encryption at rest for sensitive local data where the OS store does not
  already cover it.
- Crash and error logs the user can share deliberately; nothing is sent
  automatically.
- A code-signed installer (needs a code-signing certificate, which has a
  cost) and a safe auto-update.
- A user guide, alongside `docs/AI_GUIDE.md`.

### Phase 5: Demo broker accounts
- Exercise the Binance Testnet, Alpaca Paper and Bitget demo adapters end to
  end, with test keys the user enters.
- Complete the V5 sandbox readiness checklist (`docs/V5_SANDBOX_READINESS.md`),
  including the extended soak tests.
- An account switcher that always shows clearly which account (demo, sandbox or
  real) is active.

### Phase 6: Voice, screenshots and recording
- **Voice chat:** push-to-talk speech-to-text and spoken replies. Choice of a
  hosted service or local processing, with privacy notes for each.
- **Chart snapshots** the AI can analyse (using a vision-capable model).
- **Screenshots and screen recording** (desktop): capture a window or region,
  annotate it, and attach it to an AI conversation. Opt-in, with a visible
  "recording" indicator, and files kept locally.

### Phase 7: Any device
- A phone and tablet companion: watchlist, charts, alerts, AI chat and
  position monitoring.
- Architecture to be decided (see Open decisions). Whatever is chosen, remote
  access must be authenticated and encrypted. The API's loopback-only rule is
  never relaxed by simply opening a port; a dedicated, authenticated gateway is
  designed instead.
- Trading actions from mobile require the same confirmations and limits as
  desktop, plus device-level authentication.

### Phase 8: Real accounts
Only after phases 4 and 5 are complete and reviewed:
- An explicit written review: sandbox evidence, incident procedures
  (`docs/ORDER_SUBMISSION_INCIDENT.md`) and an extended soak.
- Hard capital limits the user sets: maximum order size, daily loss and total
  exposure.
- Manual real orders first, each with confirmation. A small, capped autonomous
  pilot only after that (README maturity gate V6).
- The project rules in `CLAUDE.md` currently say "paper trading only". They are
  changed only by the owner, deliberately, when this phase begins.

### Phase 9: Multi-user product
- User accounts and per-user data separation.
- Onboarding, help and support.
- Licensing, terms of use, privacy policy, and clear "not financial advice"
  disclaimers. Real-money features for other people may carry legal and
  regulatory obligations that depend on the country; get advice before offering
  them.

---

## 4. Open decisions

These are decided when their phase starts, not before:

| Decision | Options | Leaning |
|---|---|---|
| Mobile approach | Progressive web app; React Native app; responsive web served by a hosted backend | Web-based companion talking to the user's own engine through an authenticated gateway |
| Where the trading engine runs | User's PC only; a small always-on server; cloud | User's PC first; an always-on option later, since strategies stop when the PC sleeps |
| Voice processing | Hosted speech service; local speech models | Hosted by default (this PC is too slow for local models); local as an option on capable machines |
| AI vision for screenshots | Hosted vision model; local | Hosted, opt-in per image |
| Code signing | Buy a certificate; ship unsigned | Unsigned while personal; signed before sharing with others |

## 5. Current status

| Area | Status |
|---|---|
| Charts with live Binance data (crypto) and Yahoo (stocks) | Done |
| Live price display, 24h change | Done |
| Backtesting, optimisation, walk-forward | Done (see README maturity gates) |
| Paper trading with guarded orders and kill switch | Done (V4) |
| AI chat, strategy generation, summaries (3 providers) | Done, but the chat cannot see app data yet (Phase 2) |
| Broker sandbox readiness | In progress (V5) |
| Everything else in this roadmap | Not started |
