# Changelog

All notable changes to Astral AI. Versions follow [semantic versioning](https://semver.org);
while the version is below 1.0, any release may change behaviour.

Each version is tagged in git (`v0.2.0`) and has a GitHub release. Releases made
from `claude-work` before it is merged into `master` are marked **pre-release**.

## [Unreleased]

### Backups
- **Settings → Backups → Back up now** saves a consistent copy of the database on
  this computer (newest 10 kept). The user guide explains how to restore one.

### Mobile
- The layout works on phone-sized screens: below 768px the sidebar is a slide-in
  drawer (☰), and the chart and panels use the full width. Desktop is unchanged.
- `docs/MOBILE_ACCESS.md` proposes how a phone could reach the app safely; not built.

## [0.2.0] - 2026-11-05

Pre-release from `claude-work` (PR #13), not yet reviewed or merged into `master`.
Paper trading remains the default; real-money autonomous trading stays gated.

### Safety
- Capped-limit buys (Bitget) are risk-checked at their limit price, not the quote.
- The kill switch state and the running session are shown in a Trading session
  panel, with one-click Arm and Stop.
- Disarming needs `DISARM` typed and is limited to paper trading: refused while
  live trading is enabled or a live session runs, and live trading can't be enabled
  while disarmed. Every disarm and settings change is recorded in an audit log.
- The trading loop's log is kept across restarts in a session journal.

### Charts, watchlist and research
- Live crypto prices from Binance; RSI, MACD and ATR in their own panels.
- Watchlist is saved, editable and shows each symbol's price and daily change.
- **Gold** added (COMEX gold futures, `GC=F`).
- Price alerts with desktop notifications (checked while the app is open).
- Chart symbol, timeframe and indicators are remembered; keyboard shortcuts.
- Backtests about 40x faster; crypto backtests use the chosen period; optimizer
  searches limited to 1,000 combinations.
- Failures show their real reason instead of generic pop-ups.

### AI
- The chat can see the chart: symbol, price, indicators, simulated paper position
  and latest backtest (switchable; real account data is never sent).
- Images, pasted screenshots and video frames in chat; chats copy and save as Word.
- The sentiment badge no longer shows an invented score without AI.
- The builder's AI export includes each node's settings.

### Brokers
- Bitget demo trading and Unified Trading Account support; Test connections panel.

### Maintenance
- Backend dependencies locked with hashes; CI checks the locks and runs lint.
- Electron upgraded from 41 to 45; `npm audit` reports 0 vulnerabilities.
- User guide, AI guide and product roadmap.

## [0.1.0]

The state of `master` before the changes above.
