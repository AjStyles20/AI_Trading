import type { CandlePoint } from './indicators';

// Binance's public market-data-only hosts. They need no API key and serve the
// same spot data as api.binance.com, which is blocked on some networks.
export const BINANCE_REST_URL = 'https://data-api.binance.vision';
export const BINANCE_STREAM_URL = 'wss://data-stream.binance.vision';
export const BINANCE_MAX_KLINES = 1_000;

// Wait before each reconnect attempt; the last value repeats.
export const RECONNECT_DELAYS_MS = [1_000, 2_000, 5_000, 10_000, 30_000];

const SUPPORTED_QUOTES = new Set(['USDT', 'USDC', 'FDUSD', 'BTC', 'ETH']);

const INTERVALS: Record<string, string> = {
  '1m': '1m',
  '5m': '5m',
  '15m': '15m',
  '1h': '1h',
  '4h': '4h',
  '1D': '1d',
};

// 'BTC/USDT' -> 'BTCUSDT'. Yahoo-style 'SOL-USD' maps to the USDT pair, which
// is how Binance quotes dollars. Stock tickers ('AAPL') are not crypto pairs.
export const toBinanceSymbol = (symbol: string): string | null => {
  const match = /^([A-Za-z0-9]+)[/-]([A-Za-z]+)$/.exec(symbol.trim());
  if (!match) return null;
  const base = match[1].toUpperCase();
  const quote = match[2].toUpperCase() === 'USD' ? 'USDT' : match[2].toUpperCase();
  return SUPPORTED_QUOTES.has(quote) ? `${base}${quote}` : null;
};

export const toBinanceInterval = (timeframe: string): string | null => INTERVALS[timeframe] ?? null;

export const binanceStreamUrl = (binanceSymbol: string, interval: string): string => {
  const stream = binanceSymbol.toLowerCase();
  return `${BINANCE_STREAM_URL}/stream?streams=${stream}@kline_${interval}/${stream}@ticker`;
};

const isFiniteCandle = (candle: CandlePoint) =>
  [candle.time, candle.open, candle.high, candle.low, candle.close].every(Number.isFinite);

export const fetchBinanceKlines = async (binanceSymbol: string, interval: string, limit: number): Promise<CandlePoint[]> => {
  const params = new URLSearchParams({
    symbol: binanceSymbol,
    interval,
    limit: String(Math.min(limit, BINANCE_MAX_KLINES)),
  });
  const response = await fetch(`${BINANCE_REST_URL}/api/v3/klines?${params}`);
  if (!response.ok) throw new Error(`Binance klines request failed with HTTP ${response.status}`);
  const rows: unknown = await response.json();
  if (!Array.isArray(rows)) throw new Error('Binance klines response was not a list');
  // Row layout: [openTime ms, open, high, low, close, volume, closeTime, ...].
  return rows
    .map((row: unknown[]) => ({
      time: Number(row[0]) / 1000,
      open: Number(row[1]),
      high: Number(row[2]),
      low: Number(row[3]),
      close: Number(row[4]),
    }))
    .filter(isFiniteCandle);
};

export type LiveTicker = { price: number; change: number; percent: number };

export type StreamMessage =
  | { kind: 'kline'; candle: CandlePoint }
  | { kind: 'ticker'; ticker: LiveTicker };

// Parses one combined-stream message ({ stream, data }). Returns null for
// anything that is not a well-formed kline or 24h ticker event.
export const parseStreamMessage = (raw: string): StreamMessage | null => {
  let payload: { data?: Record<string, unknown> } & Record<string, unknown>;
  try {
    payload = JSON.parse(raw);
  } catch {
    return null;
  }
  const data = (payload.data ?? payload) as Record<string, unknown>;
  if (data.e === 'kline' && data.k && typeof data.k === 'object') {
    const k = data.k as Record<string, unknown>;
    const candle = {
      time: Number(k.t) / 1000,
      open: Number(k.o),
      high: Number(k.h),
      low: Number(k.l),
      close: Number(k.c),
    };
    return isFiniteCandle(candle) ? { kind: 'kline', candle } : null;
  }
  if (data.e === '24hrTicker') {
    const ticker = { price: Number(data.c), change: Number(data.p), percent: Number(data.P) };
    return [ticker.price, ticker.change, ticker.percent].every(Number.isFinite) && ticker.price > 0
      ? { kind: 'ticker', ticker }
      : null;
  }
  return null;
};

// Applies a live candle: replaces the forming candle, appends a new one, and
// ignores anything older than the latest candle.
export const mergeLiveCandle = (candles: CandlePoint[], candle: CandlePoint, maxLength: number): CandlePoint[] => {
  const last = candles[candles.length - 1];
  if (last && candle.time < last.time) return candles;
  const next = last && candle.time === last.time ? [...candles.slice(0, -1), candle] : [...candles, candle];
  return next.length > maxLength ? next.slice(next.length - maxLength) : next;
};
