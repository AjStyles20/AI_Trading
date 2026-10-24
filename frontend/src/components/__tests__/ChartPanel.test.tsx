import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import axios from 'axios';
import ChartPanel from '../ChartPanel';
import { getRefreshIntervalMs } from '../../lib/liveRefresh';
import { formatPrice, get24hChange, getPriceDirection } from '../../lib/priceTicker';

type MockSeries = { kind: string; setData: ReturnType<typeof vi.fn> };
type MockChart = {
  series: MockSeries[];
  fitContent: ReturnType<typeof vi.fn>;
  remove: ReturnType<typeof vi.fn>;
  // Stands in for the real chart's own wheel (zoom) handler on its drawing surface.
  wheel: Mock<(event: Event) => void>;
  surface: HTMLElement;
};

const charts: MockChart[] = [];

vi.mock('lightweight-charts', () => ({
  ColorType: { Solid: 'solid' },
  CandlestickSeries: 'Candlestick',
  LineSeries: 'Line',
  createSeriesMarkers: () => ({ setMarkers: vi.fn() }),
  createChart: (container: HTMLElement) => {
    const surface = document.createElement('div');
    container.appendChild(surface);
    const chart: MockChart = { series: [], fitContent: vi.fn(), remove: vi.fn(), wheel: vi.fn<(event: Event) => void>(), surface };
    surface.addEventListener('wheel', (event) => chart.wheel(event));
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

describe('price ticker helpers', () => {
  it('formats normal and sub-1 prices', () => {
    expect(formatPrice(81518.594)).toBe('81,518.59');
    expect(formatPrice(0.000123456)).toBe('0.0001235');
    expect(formatPrice(-212.5, { signed: true })).toBe('-212.50');
    expect(formatPrice(3, { signed: true })).toBe('+3.00');
  });

  it('reports the direction of a price move', () => {
    expect(getPriceDirection(null, 10)).toBe('flat');
    expect(getPriceDirection(10, 10)).toBe('flat');
    expect(getPriceDirection(10, 11)).toBe('up');
    expect(getPriceDirection(10, 9)).toBe('down');
  });

  it('measures change against the close 24 hours before the latest candle', () => {
    const day = 86_400;
    const series = [
      { time: 0, open: 1, high: 1, low: 1, close: 100 },
      { time: day / 2, open: 1, high: 1, low: 1, close: 150 },
      { time: day, open: 1, high: 1, low: 1, close: 110 },
    ];
    expect(get24hChange(series)).toEqual({ change: 10, percent: 10 });
    expect(get24hChange(series.slice(1))).toBeNull();
    expect(get24hChange([])).toBeNull();
  });
});

describe('ChartPanel live price', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    charts.length = 0;
    post.mockReset();
    setVisibility('visible');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const refresh = () => act(async () => { await vi.advanceTimersByTimeAsync(getRefreshIntervalMs('1h')); });

  it('shows the latest price neutrally on first load', async () => {
    post.mockResolvedValue({ data: candles(105) });
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();

    const price = screen.getByTestId('last-price');
    expect(price).toHaveTextContent('105.00');
    expect(price).toHaveAttribute('data-direction', 'flat');
    expect(price).toHaveClass('text-white');
  });

  it('turns green and flashes when a live refresh moves the price up', async () => {
    post.mockResolvedValueOnce({ data: candles(105) }).mockResolvedValue({ data: candles(108.5) });
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();
    await refresh();

    const price = screen.getByTestId('last-price');
    expect(price).toHaveTextContent('108.50');
    expect(price).toHaveAttribute('data-direction', 'up');
    expect(price).toHaveClass('text-green-400', 'bg-green-500/25');

    await act(async () => { await vi.advanceTimersByTimeAsync(700); });
    expect(price).toHaveClass('text-green-400', 'bg-transparent');
  });

  it('turns red when a live refresh moves the price down, and stays red while unchanged', async () => {
    post
      .mockResolvedValueOnce({ data: candles(105) })
      .mockResolvedValueOnce({ data: candles(101) })
      .mockResolvedValue({ data: candles(101) });
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();
    await refresh();

    const price = screen.getByTestId('last-price');
    expect(price).toHaveAttribute('data-direction', 'down');
    expect(price).toHaveClass('text-red-400', 'bg-red-500/25');

    await refresh();
    expect(price).toHaveAttribute('data-direction', 'down');
    expect(price).toHaveClass('text-red-400', 'bg-transparent');
  });

  it('resets to neutral when switching timeframe instead of comparing across loads', async () => {
    post
      .mockResolvedValueOnce({ data: candles(105) })
      .mockResolvedValueOnce({ data: candles(120) })
      .mockResolvedValue({ data: candles(90) });
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();
    await refresh();
    expect(screen.getByTestId('last-price')).toHaveAttribute('data-direction', 'up');

    fireEvent.click(screen.getByText('1m'));
    await flush();
    expect(screen.getByTestId('last-price')).toHaveTextContent('90.00');
    expect(screen.getByTestId('last-price')).toHaveAttribute('data-direction', 'flat');
  });

  it('shows the 24h change in green or red when history covers a day', async () => {
    const day = [
      { timestamp: '2026-10-22T11:00:00Z', open: 100, high: 100, low: 100, close: 200 },
      { timestamp: '2026-10-23T11:00:00Z', open: 100, high: 100, low: 100, close: 190 },
    ];
    post.mockResolvedValue({ data: day });
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();

    const change = screen.getByTestId('day-change');
    expect(change).toHaveTextContent('-10.00 (-5.00%) 24h');
    expect(change).toHaveClass('text-red-400');
  });

  it('hides the 24h change when history is shorter than a day', async () => {
    post.mockResolvedValue({ data: candles(105) });
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();
    expect(screen.queryByTestId('day-change')).not.toBeInTheDocument();
  });
});

describe('ChartPanel mouse wheel', () => {
  beforeEach(() => {
    charts.length = 0;
    post.mockReset();
    post.mockResolvedValue({ data: candles(105) });
  });

  it('leaves a plain wheel to scroll the page instead of zooming the chart', () => {
    render(<ChartPanel symbol="BTC/USDT" />);
    const wheel = new WheelEvent('wheel', { deltaY: -120, bubbles: true, cancelable: true });
    charts[0].surface.dispatchEvent(wheel);

    expect(charts[0].wheel).not.toHaveBeenCalled();
    expect(wheel.defaultPrevented).toBe(false);
  });

  it('passes Ctrl + wheel and Cmd + wheel to the chart for zooming', () => {
    render(<ChartPanel symbol="BTC/USDT" />);
    fireEvent.wheel(charts[0].surface, { deltaY: -120, ctrlKey: true });
    fireEvent.wheel(charts[0].surface, { deltaY: -120, metaKey: true });

    expect(charts[0].wheel).toHaveBeenCalledTimes(2);
  });
});
