# Astral AI: user guide

Astral is a personal trading companion: charts, research, backtests and paper
trading on your own computer. It is engineering and research software, not
financial advice, and no backtest proves future profit.

For AI setup see `AI_GUIDE.md`. For the safety rules see `SAFETY_BASELINE.md`.

## The screen

- **Left:** watchlist, price alerts and the AI chat.
- **Centre:** the price chart and its indicator panels, or the Strategy Builder.
- **Below the chart:** strategy actions, backtest settings, the account panel,
  and the tabs Strategy Code, Backtest Results, Optimize, Open Positions and
  Terminal Logs.

## Watchlist

- Click a symbol to chart it. Each symbol shows its price and change since the
  previous daily close, refreshed about once a minute.
- Search with a ticker (`AAPL`) or a pair (`SOL-USD`, `BTC/USDT`). A symbol is
  added only if market data loads for it. Yahoo Finance sometimes returns
  nothing for a moment, so if a real ticker fails, try again shortly.
- Hover over a symbol and click **×** to remove it. Your list is remembered.

Watchlist prices come from Yahoo Finance. The crypto chart header streams from
Binance, so the two can differ slightly.

## Chart

Your symbol, timeframe and indicators are remembered between sessions.

| Keys | Action |
|---|---|
| `1` to `6` | Timeframe 1m, 5m, 15m, 1h, 4h, 1D |
| `S` `E` `R` | Toggle SMA 20, EMA 21, RSI 14 |
| `M` `B` `A` | Toggle MACD, Bollinger Bands, ATR 14 |
| `/` | Jump to the watchlist search |
| `?` | Show or hide the shortcut list |
| `Esc` | Close the shortcut list or the expanded chat |

Shortcuts are ignored while you type in a field.

The sentiment badge shows a score only when an AI provider actually scored
recent headlines. Otherwise it reads **Sentiment needs AI** or **No sentiment**;
hover over it for the reason.

## Price alerts

Open **Price alerts** under the watchlist, choose at-or-above or at-or-below for
the symbol on screen, enter a price and click **Add**.

- Alerts are checked about every 30 seconds **only while Astral is open**. They
  do not fire while it is closed.
- A triggered alert stays listed with the price it hit, and raises a desktop
  notification where notifications are allowed.
- Alerts only notify you. They never place orders.

## Strategies and backtests

1. Create a strategy with **Generate** (needs an AI provider) or the Strategy
   Builder's **Local Export** (no AI needed).
2. Click **Validate**, then **Run Backtest**. Results appear in Backtest Results,
   and if a run fails, the reason appears there too.
3. **Save** keeps a strategy as a workspace you can reload, tag and archive.

**Optimize** tries combinations of parameter values, up to 1,000 per search.
Larger searches are refused, because more combinations mostly add overfitting.
Results include warnings about weak evidence, so read them.

## AI chat

With a provider configured, the chat can see what is on your screen. **Share
chart** in the chat header sends the symbol, timeframe, price, indicator values
and latest backtest summary with each message. That data goes to the provider
you chose. Turn the switch off to stop sending it.

The AI can explain and suggest. It cannot place, change or cancel orders.

## Trading and safety

Paper trading is the default and uses simulated money. The account panel always
labels the kind of money shown.

- **Kill switch:** on by default. While armed, the trading loop only observes and
  creates no orders.
- **Risk limits:** order size, position size, daily loss and drawdown limits are
  checked before any order.
- **Live trading:** locked unless you deliberately enable it. Real-money
  autonomous trading remains gated; see the README's maturity gates.

## Settings history

**Terminal Logs** lists recent settings changes, including kill switch and risk
limit changes with their old and new values. API keys are listed by name only;
their values are never recorded.

## Where your data lives

Settings, strategies, trades, alerts and chat history are in a local SQLite
database. API keys are in your operating system's credential store. Nothing is
sent anywhere except your chosen AI provider (when you use the AI), and the
market-data and broker services the app connects to.
