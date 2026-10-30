import type { AssetType } from '../components/BottomPanel';

export const WATCHLIST_KEY = 'astral.watchlist';
export const DEFAULT_WATCHLIST = ['BTC/USDT', 'ETH/USDT', 'AAPL', 'NVDA', 'TSLA', 'SOL-USD'];
export const MAX_WATCHLIST = 30;

export type Quote = { price: number; changePct: number | null };

// Pairs ('BTC/USDT', 'SOL-USD') are crypto; plain tickers ('AAPL') are stocks.
export const assetTypeFor = (symbol: string): AssetType =>
  symbol.includes('/') || symbol.includes('-') ? 'crypto' : 'stock';

// Upper-case and trim, keeping only characters tickers and pairs use.
export const normalizeSymbol = (raw: string): string | null => {
  const symbol = raw.trim().toUpperCase();
  return /^[A-Z0-9^][A-Z0-9.=^/-]{0,19}$/.test(symbol) ? symbol : null;
};

// The backend's quote route takes the symbol as a path segment, so '/' becomes '-'.
export const quotePath = (symbol: string): string =>
  `/api/market/quote/${assetTypeFor(symbol)}/${encodeURIComponent(symbol.replace('/', '-'))}`;

export const readWatchlist = (): string[] => {
  try {
    const stored = JSON.parse(window.localStorage.getItem(WATCHLIST_KEY) ?? 'null');
    if (!Array.isArray(stored)) return DEFAULT_WATCHLIST;
    const symbols = stored
      .map((item) => (typeof item === 'string' ? normalizeSymbol(item) : null))
      .filter((item): item is string => item !== null);
    return Array.from(new Set(symbols)).slice(0, MAX_WATCHLIST);
  } catch {
    return DEFAULT_WATCHLIST;
  }
};

export const storeWatchlist = (symbols: string[]) => {
  try {
    window.localStorage.setItem(WATCHLIST_KEY, JSON.stringify(symbols));
  } catch {
    // Storage unavailable (private window); the list still applies for this session.
  }
};

// Reads the backend's quote body, accepting only finite positive prices.
export const parseQuote = (data: unknown): Quote | null => {
  const body = data as { price?: unknown; change_pct?: unknown } | null;
  const price = Number(body?.price);
  if (!Number.isFinite(price) || price <= 0) return null;
  const change = body?.change_pct === null || body?.change_pct === undefined ? null : Number(body.change_pct);
  return { price, changePct: change !== null && Number.isFinite(change) ? change : null };
};

export const formatChange = (changePct: number): string =>
  `${changePct > 0 ? '+' : ''}${changePct.toFixed(2)}%`;
