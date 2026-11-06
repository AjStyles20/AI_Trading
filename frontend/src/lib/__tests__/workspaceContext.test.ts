import { describe, expect, it } from 'vitest';
import { buildWorkspaceContext, latestIndicators, type ChartSnapshot } from '../workspaceContext';

const chart: ChartSnapshot = {
  symbol: 'BTC/USDT',
  timeframe: '1h',
  last_price: 80000,
  change_24h_pct: -0.3,
  price_source: 'binance',
  indicators: { rsi14: 41.2 },
};

const candles = Array.from({ length: 60 }, (_, i) => {
  const close = 100 + Math.sin(i / 4) * 5 + i * 0.1;
  return { time: 1_700_000_000 + i * 3600, open: close - 0.5, high: close + 1, low: close - 1, close };
});

describe('workspace context', () => {
  it('combines the chart snapshot with the symbol and latest backtest', () => {
    const context = buildWorkspaceContext('BTC/USDT', 'crypto', chart, {
      total_return_pct: 4.2, max_drawdown_pct: -7.5, trade_count: 31, win_rate_pct: 48,
      buy_hold_return_pct: 12.1, scenario: { interval: '1h', period: '6mo' },
    });

    expect(context).toEqual({
      symbol: 'BTC/USDT', asset_type: 'crypto', timeframe: '1h', last_price: 80000, change_24h_pct: -0.3,
      price_source: 'binance', indicators: { rsi14: 41.2 },
      backtest: { total_return_pct: 4.2, max_drawdown_pct: -7.5, trade_count: 31, win_rate_pct: 48, buy_hold_return_pct: 12.1, interval: '1h', period: '6mo' },
    });
  });

  it('sends nothing while the chart still shows the previous symbol', () => {
    expect(buildWorkspaceContext('AAPL', 'stock', chart, null)).toBeNull();
    expect(buildWorkspaceContext('AAPL', 'stock', null, null)).toBeNull();
  });

  it('leaves out non-finite numbers and unknown backtest scenarios', () => {
    const context = buildWorkspaceContext('BTC/USDT', 'crypto', { ...chart, last_price: NaN, change_24h_pct: Infinity }, {
      total_return_pct: 1, max_drawdown_pct: -2, trade_count: 3, win_rate_pct: NaN, scenario: { interval: '7m', period: 'forever' },
    });

    expect(context?.last_price).toBeUndefined();
    expect(context?.change_24h_pct).toBeUndefined();
    expect(context?.backtest).toEqual({ total_return_pct: 1, max_drawdown_pct: -2, trade_count: 3 });
  });

  it('skips a backtest without the core figures', () => {
    expect(buildWorkspaceContext('BTC/USDT', 'crypto', chart, { total_return_pct: 3 })?.backtest).toBeUndefined();
  });

  it('reports the latest finite indicator values', () => {
    const values = latestIndicators(candles);

    expect(Object.keys(values).sort()).toEqual(['atr14', 'bb_lower', 'bb_upper', 'ema21', 'macd', 'macd_signal', 'rsi14', 'sma20']);
    expect(Object.values(values).every(Number.isFinite)).toBe(true);
    expect(values.rsi14).toBeGreaterThanOrEqual(0);
    expect(values.rsi14).toBeLessThanOrEqual(100);
    expect(latestIndicators([])).toEqual({});
  });
});
