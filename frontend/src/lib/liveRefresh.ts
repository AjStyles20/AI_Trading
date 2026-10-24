// How often the chart re-fetches price history for each timeframe. Short enough
// that the forming candle visibly moves, long enough to stay gentle on the
// upstream data provider (Yahoo Finance via the backend).
const REFRESH_INTERVAL_MS: Record<string, number> = {
  '1m': 15_000,
  '5m': 30_000,
  '15m': 60_000,
  '1h': 60_000,
  '4h': 120_000,
  '1D': 300_000,
};

export const DEFAULT_REFRESH_INTERVAL_MS = 60_000;

export const getRefreshIntervalMs = (timeframe: string): number =>
  REFRESH_INTERVAL_MS[timeframe] ?? DEFAULT_REFRESH_INTERVAL_MS;

// How many candles to request. Enough for a full day on the short timeframes so
// the 24h change can be computed, without downloading the provider's whole
// period on every refresh.
const HISTORY_LIMIT: Record<string, number> = {
  '1m': 1_500,
  '5m': 600,
};

export const DEFAULT_HISTORY_LIMIT = 500;

export const getHistoryLimit = (timeframe: string): number =>
  HISTORY_LIMIT[timeframe] ?? DEFAULT_HISTORY_LIMIT;

// Candles in view when a chart first loads; older history stays a drag away.
export const INITIAL_VISIBLE_CANDLES = 150;
