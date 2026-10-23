import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import ChartPanel from '../ChartPanel';
import { getRefreshIntervalMs } from '../../lib/liveRefresh';

type MockSeries = { kind: string; setData: ReturnType<typeof vi.fn> };
type MockChart = { series: MockSeries[]; fitContent: ReturnType<typeof vi.fn>; remove: ReturnType<typeof vi.fn> };

const charts: MockChart[] = [];

vi.mock('lightweight-charts', () => ({
  ColorType: { Solid: 'solid' },
  CandlestickSeries: 'Candlestick',
  LineSeries: 'Line',
  createSeriesMarkers: () => ({ setMarkers: vi.fn() }),
  createChart: () => {
    const chart: MockChart = { series: [], fitContent: vi.fn(), remove: vi.fn() };
    charts.push(chart);
    return {
      addSeries: (kind: string) => {
        const series = { kind, setData: vi.fn() };
        chart.series.push(series);
        return series;
      },
      timeScale: () => ({ fitContent: chart.fitContent }),
      applyOptions: vi.fn(),
      remove: chart.remove,
    };
  },
}));

vi.mock('axios', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: { sentiment_score: 0.5, sentiment_label: 'Neutral' } })),
    post: vi.fn(),
    isAxiosError: () => false,
  },
}));

const post = vi.mocked(axios.post);

const candles = (close: number) => [
  { timestamp: '2026-10-23T10:00:00Z', open: 100, high: 110, low: 90, close: 105 },
  { timestamp: '2026-10-23T11:00:00Z', open: 105, high: 115, low: 95, close },
];

const candleSeries = (chart: MockChart) => chart.series.find((series) => series.kind === 'Candlestick')!;
const flush = () => act(async () => { await vi.advanceTimersByTimeAsync(0); });
const setVisibility = (state: 'visible' | 'hidden') =>
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });

describe('ChartPanel live refresh', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    charts.length = 0;
    post.mockReset();
    setVisibility('visible');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('maps every timeframe to a refresh interval', () => {
    expect(getRefreshIntervalMs('1m')).toBe(15_000);
    expect(getRefreshIntervalMs('1h')).toBe(60_000);
    expect(getRefreshIntervalMs('1D')).toBe(300_000);
    expect(getRefreshIntervalMs('unknown')).toBe(60_000);
  });

  it('refreshes in the background without the loading overlay or a view reset', async () => {
    post.mockResolvedValueOnce({ data: candles(105) }).mockResolvedValue({ data: candles(108) });
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();

    expect(post).toHaveBeenCalledTimes(1);
    expect(charts[0].fitContent).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('live-status')).toHaveTextContent('Live · updated');

    await act(async () => { await vi.advanceTimersByTimeAsync(getRefreshIntervalMs('1h') - 1); });
    expect(post).toHaveBeenCalledTimes(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(post).toHaveBeenCalledTimes(2);
    expect(screen.queryByText(/Syncing Price Data/i)).not.toBeInTheDocument();
    expect(candleSeries(charts[0]).setData).toHaveBeenLastCalledWith(
      expect.arrayContaining([expect.objectContaining({ close: 108 })]),
    );
    expect(charts[0].fitContent).toHaveBeenCalledTimes(1);
  });

  it('keeps the last good chart when a background refresh fails', async () => {
    post.mockResolvedValueOnce({ data: candles(105) }).mockRejectedValue(new Error('network down'));
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();

    await act(async () => { await vi.advanceTimersByTimeAsync(getRefreshIntervalMs('1h')); });

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByTestId('live-status')).toHaveTextContent('Update failed');
    expect(candleSeries(charts[0]).setData).toHaveBeenCalledTimes(1);
  });

  it('skips refreshes while the tab is hidden and catches up when shown', async () => {
    post.mockResolvedValue({ data: candles(105) });
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();

    setVisibility('hidden');
    await act(async () => { await vi.advanceTimersByTimeAsync(getRefreshIntervalMs('1h') * 3); });
    expect(post).toHaveBeenCalledTimes(1);

    setVisibility('visible');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('discards a late response for a timeframe that is no longer selected', async () => {
    let resolveStale!: (value: { data: ReturnType<typeof candles> }) => void;
    post
      .mockImplementationOnce(() => new Promise((resolve) => { resolveStale = resolve; }))
      .mockResolvedValue({ data: candles(200) });
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();

    fireEvent.click(screen.getByText('1m'));
    await flush();
    await act(async () => {
      resolveStale({ data: candles(999) });
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(candleSeries(charts[0]).setData).not.toHaveBeenCalled();
    const current = candleSeries(charts[charts.length - 1]);
    expect(current.setData).toHaveBeenCalledTimes(1);
    expect(current.setData).toHaveBeenLastCalledWith(
      expect.arrayContaining([expect.objectContaining({ close: 200 })]),
    );
  });
});
