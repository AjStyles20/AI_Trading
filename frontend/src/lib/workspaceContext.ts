import type { AssetType, BacktestResults } from '../components/BottomPanel';
import {
  calculateATR,
  calculateBollingerBands,
  calculateEMA,
  calculateMACD,
  calculateRSI,
  calculateSMA,
  type CandlePoint,
} from './indicators';

// What the chat sends so the AI can see the user's screen. The backend
// validates the same shape (backend/ai_engine/workspace_context.py).

export type ChartSnapshot = {
  // The symbol the chart showed when the snapshot was taken.
  symbol: string;
  timeframe: string;
  last_price?: number;
  change_24h_pct?: number;
  price_source?: 'binance' | 'backend';
  indicators: Record<string, number>;
};

export type WorkspaceContext = Omit<ChartSnapshot, 'symbol'> & {
  symbol: string;
  asset_type: AssetType;
  backtest?: {
    interval?: string;
    period?: string;
    total_return_pct: number;
    max_drawdown_pct: number;
    buy_hold_return_pct?: number;
    win_rate_pct?: number;
    trade_count: number;
  };
};

const BACKTEST_INTERVALS = new Set(['1m', '5m', '15m', '1h', '4h', '1d']);
const BACKTEST_PERIODS = new Set(['1mo', '3mo', '6mo', '1y', '2y']);

const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const last = <T,>(points: T[]): T | undefined => points[points.length - 1];

// Latest value of each indicator the AI may be told about; non-finite values are left out.
export const latestIndicators = (candles: CandlePoint[]): Record<string, number> => {
  if (candles.length === 0) return {};
  const macd = last(calculateMACD(candles));
  const bands = last(calculateBollingerBands(candles));
  const values: Record<string, number | undefined> = {
    sma20: last(calculateSMA(candles, 20))?.value,
    ema21: last(calculateEMA(candles, 21))?.value,
    rsi14: last(calculateRSI(candles, 14))?.value,
    macd: macd?.macd,
    macd_signal: macd?.signal,
    bb_upper: bands?.upper,
    bb_lower: bands?.lower,
    atr14: last(calculateATR(candles, 14))?.value,
  };
  return Object.fromEntries(Object.entries(values).filter((entry): entry is [string, number] => finite(entry[1])));
};

export const buildWorkspaceContext = (
  symbol: string,
  assetType: AssetType,
  chart: ChartSnapshot | null,
  backtest: BacktestResults | null,
): WorkspaceContext | null => {
  // Right after a symbol switch the chart may still describe the old symbol;
  // sending its price under the new name would mislead the AI.
  if (!chart || chart.symbol !== symbol) return null;
  const context: WorkspaceContext = { symbol, asset_type: assetType, timeframe: chart.timeframe, indicators: chart.indicators };
  if (finite(chart.last_price) && chart.last_price > 0) context.last_price = chart.last_price;
  if (finite(chart.change_24h_pct)) context.change_24h_pct = chart.change_24h_pct;
  if (chart.price_source) context.price_source = chart.price_source;
  if (backtest && finite(backtest.total_return_pct) && finite(backtest.max_drawdown_pct) && finite(backtest.trade_count)) {
    context.backtest = {
      total_return_pct: backtest.total_return_pct,
      max_drawdown_pct: backtest.max_drawdown_pct,
      trade_count: Math.max(0, Math.round(backtest.trade_count)),
    };
    if (finite(backtest.buy_hold_return_pct)) context.backtest.buy_hold_return_pct = backtest.buy_hold_return_pct;
    if (finite(backtest.win_rate_pct)) context.backtest.win_rate_pct = backtest.win_rate_pct;
    const { interval, period } = backtest.scenario ?? {};
    if (interval && BACKTEST_INTERVALS.has(interval)) context.backtest.interval = interval;
    if (period && BACKTEST_PERIODS.has(period)) context.backtest.period = period;
  }
  return context;
};
