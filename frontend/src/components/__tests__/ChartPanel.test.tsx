import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import axios from 'axios';
import ChartPanel from '../ChartPanel';
import { getRefreshIntervalMs } from '../../lib/liveRefresh';
import { formatPrice, get24hChange, getPriceDirection } from '../../lib/priceTicker';
import { mergeLiveCandle, parseStreamMessage, toBinanceSymbol } from '../../lib/binanceMarket';

type MockSeries = {
  kind: string;
  paneIndex: number;
  removed: boolean;
  priceLines: number[];
  setData: ReturnType<typeof vi.fn>;
  update: ReturnType<typeof vi.fn>;
};

// Stands in for the browser WebSocket; tests drive open/messages/drops by hand.
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  closed = false;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
  close() { this.closed = true; }
  open() { this.onopen?.(new Event('open')); }
  emit(data: unknown) { this.onmessage?.(new MessageEvent('message', { data: JSON.stringify({ stream: 'test', data }) })); }
  drop() { this.onclose?.(new CloseEvent('close')); }
}

// No test may reach the real network: Binance history is offline unless a test
// provides it, and live connections are fakes.
const fetchMock = vi.fn<(url: string) => Promise<unknown>>();
beforeEach(() => {
  FakeWebSocket.instances = [];
  fetchMock.mockReset();
  fetchMock.mockRejectedValue(new Error('offline'));
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('WebSocket', FakeWebSocket);
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
type MockChart = {
  series: MockSeries[];
  fitContent: ReturnType<typeof vi.fn>;
  setVisibleLogicalRange: ReturnType<typeof vi.fn>;
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
  HistogramSeries: 'Histogram',
  createSeriesMarkers: () => ({ setMarkers: vi.fn() }),
  createChart: (container: HTMLElement) => {
    const surface = document.createElement('div');
    container.appendChild(surface);
    const chart: MockChart = { series: [], fitContent: vi.fn(), setVisibleLogicalRange: vi.fn(), remove: vi.fn(), wheel: vi.fn<(event: Event) => void>(), surface };
    surface.addEventListener('wheel', (event) => chart.wheel(event));
    charts.push(chart);
    // Panels exist while they hold a series, as in the real chart.
    const livePanes = () => Math.max(0, ...chart.series.filter((s) => !s.removed).map((s) => s.paneIndex)) + 1;
    return {
      addSeries: (kind: string, _options?: unknown, paneIndex = 0) => {
        const series: MockSeries = {
          kind, paneIndex, removed: false, priceLines: [], setData: vi.fn(), update: vi.fn(),
        };
        chart.series.push(series);
        return { ...series, createPriceLine: (line: { price: number }) => series.priceLines.push(line.price),
          setData: series.setData, update: series.update, _mock: series };
      },
      removeSeries: (handle: { _mock: MockSeries }) => { handle._mock.removed = true; },
      panes: () => Array.from({ length: livePanes() }, () => ({ setStretchFactor: vi.fn() })),
      removePane: vi.fn(),
      timeScale: () => ({ fitContent: chart.fitContent, setVisibleLogicalRange: chart.setVisibleLogicalRange }),
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
// Runs due timers, then drains chained promises (history fallbacks take a few hops).
const advance = (ms: number) => act(async () => {
  await vi.advanceTimersByTimeAsync(ms);
  for (let i = 0; i < 5; i += 1) await vi.advanceTimersByTimeAsync(0);
});
const flush = () => advance(0);
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
    render(<ChartPanel symbol="AAPL" />);
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
    render(<ChartPanel symbol="AAPL" />);
    await flush();

    await act(async () => { await vi.advanceTimersByTimeAsync(getRefreshIntervalMs('1h')); });

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByTestId('live-status')).toHaveTextContent('Update failed');
    expect(candleSeries(charts[0]).setData).toHaveBeenCalledTimes(1);
  });

  it('skips refreshes while the tab is hidden and catches up when shown', async () => {
    post.mockResolvedValue({ data: candles(105) });
    render(<ChartPanel symbol="AAPL" />);
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
    render(<ChartPanel symbol="AAPL" />);
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
    render(<ChartPanel symbol="AAPL" />);
    await flush();

    const price = screen.getByTestId('last-price');
    expect(price).toHaveTextContent('105.00');
    expect(price).toHaveAttribute('data-direction', 'flat');
    expect(price).toHaveClass('text-white');
  });

  it('turns green and flashes when a live refresh moves the price up', async () => {
    post.mockResolvedValueOnce({ data: candles(105) }).mockResolvedValue({ data: candles(108.5) });
    render(<ChartPanel symbol="AAPL" />);
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
    render(<ChartPanel symbol="AAPL" />);
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
    render(<ChartPanel symbol="AAPL" />);
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
    render(<ChartPanel symbol="AAPL" />);
    await flush();

    const change = screen.getByTestId('day-change');
    expect(change).toHaveTextContent('-10.00 (-5.00%) 24h');
    expect(change).toHaveClass('text-red-400');
  });

  it('hides the 24h change when history is shorter than a day', async () => {
    post.mockResolvedValue({ data: candles(105) });
    render(<ChartPanel symbol="AAPL" />);
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
    render(<ChartPanel symbol="AAPL" />);
    const wheel = new WheelEvent('wheel', { deltaY: -120, bubbles: true, cancelable: true });
    charts[0].surface.dispatchEvent(wheel);

    expect(charts[0].wheel).not.toHaveBeenCalled();
    expect(wheel.defaultPrevented).toBe(false);
  });

  it('passes Ctrl + wheel and Cmd + wheel to the chart for zooming', () => {
    render(<ChartPanel symbol="AAPL" />);
    fireEvent.wheel(charts[0].surface, { deltaY: -120, ctrlKey: true });
    fireEvent.wheel(charts[0].surface, { deltaY: -120, metaKey: true });

    expect(charts[0].wheel).toHaveBeenCalledTimes(2);
  });
});

describe('ChartPanel history window', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    charts.length = 0;
    post.mockReset();
    setVisibility('visible');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const manyCandles = (count: number) => Array.from({ length: count }, (_, i) => ({
    timestamp: new Date(Date.UTC(2026, 9, 23, 0, i)).toISOString(), open: 100, high: 101, low: 99, close: 100,
  }));

  it('requests a day of candles on 1m and the default elsewhere', async () => {
    post.mockResolvedValue({ data: candles(105) });
    render(<ChartPanel symbol="AAPL" />);
    await flush();
    expect(post).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ interval: '1h', limit: 500 }));

    fireEvent.click(screen.getByText('1m'));
    await flush();
    expect(post).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ interval: '1m', limit: 1_500 }));
  });

  it('opens on the most recent candles instead of squeezing the whole history into view', async () => {
    post.mockResolvedValue({ data: manyCandles(1_000) });
    render(<ChartPanel symbol="AAPL" />);
    await flush();

    expect(charts[0].fitContent).not.toHaveBeenCalled();
    expect(charts[0].setVisibleLogicalRange).toHaveBeenCalledWith({ from: 850, to: 1_002 });
  });
});

describe('Binance market helpers', () => {
  it('maps crypto pairs to Binance symbols and leaves stocks alone', () => {
    expect(toBinanceSymbol('BTC/USDT')).toBe('BTCUSDT');
    expect(toBinanceSymbol('eth/usdt')).toBe('ETHUSDT');
    expect(toBinanceSymbol('SOL-USD')).toBe('SOLUSDT');
    expect(toBinanceSymbol('AAPL')).toBeNull();
    expect(toBinanceSymbol('BTC/EUR')).toBeNull();
  });

  it('parses kline and ticker messages and rejects anything malformed', () => {
    expect(parseStreamMessage(JSON.stringify({ data: { e: 'kline', k: { t: 60_000, o: '1', h: '2', l: '0.5', c: '1.5' } } })))
      .toEqual({ kind: 'kline', candle: { time: 60, open: 1, high: 2, low: 0.5, close: 1.5 } });
    expect(parseStreamMessage(JSON.stringify({ data: { e: '24hrTicker', c: '101.5', p: '-2', P: '-1.93' } })))
      .toEqual({ kind: 'ticker', ticker: { price: 101.5, change: -2, percent: -1.93 } });
    expect(parseStreamMessage('not json')).toBeNull();
    expect(parseStreamMessage(JSON.stringify({ data: { e: 'kline', k: { t: 1, o: 'x', h: '1', l: '1', c: '1' } } }))).toBeNull();
    expect(parseStreamMessage(JSON.stringify({ data: { e: '24hrTicker', c: '0', p: '0', P: '0' } }))).toBeNull();
    expect(parseStreamMessage(JSON.stringify({ data: { e: 'trade' } }))).toBeNull();
  });

  it('merges live candles by replacing, appending, capping and ignoring stale ones', () => {
    const at = (time: number, close: number) => ({ time, open: 1, high: 1, low: 1, close });
    const base = [at(1, 10), at(2, 20)];
    expect(mergeLiveCandle(base, at(2, 25), 10)).toEqual([at(1, 10), at(2, 25)]);
    expect(mergeLiveCandle(base, at(3, 30), 10)).toEqual([at(1, 10), at(2, 20), at(3, 30)]);
    expect(mergeLiveCandle(base, at(3, 30), 2)).toEqual([at(2, 20), at(3, 30)]);
    expect(mergeLiveCandle(base, at(1, 99), 10)).toBe(base);
  });
});

describe('ChartPanel Binance live stream', () => {
  const HOUR_MS = 3_600_000;
  const START_MS = Date.UTC(2026, 9, 23, 10);
  // Binance kline rows: [openTime ms, open, high, low, close, volume, closeTime].
  const klineRows = (closes: number[]) =>
    closes.map((close, i) => [START_MS + i * HOUR_MS, '100', '130', '90', String(close), '1', 0]);
  const binanceHistory = (closes: number[]) =>
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve(klineRows(closes)) });
  const socket = (index = FakeWebSocket.instances.length - 1) => FakeWebSocket.instances[index];
  const status = () => screen.getByTestId('live-status');

  beforeEach(() => {
    vi.useFakeTimers();
    charts.length = 0;
    post.mockReset();
    post.mockResolvedValue({ data: candles(105) });
    setVisibility('visible');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads crypto history from Binance and opens a live stream for it', async () => {
    binanceHistory([110, 120]);
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = fetchMock.mock.calls[0][0];
    expect(url).toContain('data-api.binance.vision/api/v3/klines');
    expect(url).toContain('symbol=BTCUSDT');
    expect(url).toContain('interval=1h');
    expect(url).toContain('limit=500');
    expect(post).not.toHaveBeenCalled();
    expect(candleSeries(charts[0]).setData).toHaveBeenCalledWith([
      { time: START_MS / 1000, open: 100, high: 130, low: 90, close: 110 },
      { time: START_MS / 1000 + 3_600, open: 100, high: 130, low: 90, close: 120 },
    ]);

    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(socket().url).toBe('wss://data-stream.binance.vision/stream?streams=btcusdt@kline_1h/btcusdt@ticker');
    expect(status()).toHaveTextContent('Connecting to Binance');

    act(() => socket().open());
    expect(status()).toHaveTextContent('Live · Binance');
  });

  it('updates the forming candle and the price from the stream', async () => {
    binanceHistory([110, 120]);
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();
    act(() => socket().open());

    act(() => socket().emit({ e: 'kline', k: { t: START_MS + HOUR_MS, o: '100', h: '135', l: '90', c: '125' } }));
    expect(candleSeries(charts[0]).update).toHaveBeenLastCalledWith(
      { time: START_MS / 1000 + 3_600, open: 100, high: 135, low: 90, close: 125 },
    );

    act(() => socket().emit({ e: '24hrTicker', c: '126.5', p: '-3.5', P: '-2.69' }));
    const price = screen.getByTestId('last-price');
    expect(price).toHaveTextContent('126.50');
    expect(price).toHaveAttribute('data-direction', 'up');
    expect(price).toHaveClass('text-green-400', 'bg-green-500/25');
    expect(screen.getByTestId('day-change')).toHaveTextContent('-3.50 (-2.69%) 24h');
    expect(screen.getByTestId('day-change')).toHaveClass('text-red-400');

    act(() => socket().emit({ e: '24hrTicker', c: '126.1', p: '-3.9', P: '-3.00' }));
    expect(price).toHaveTextContent('126.10');
    expect(price).toHaveAttribute('data-direction', 'down');
    expect(price).toHaveClass('text-red-400', 'bg-red-500/25');
  });

  it('does not poll for history while streaming', async () => {
    binanceHistory([110, 120]);
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();
    act(() => socket().open());

    await advance(10 * 60_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(post).not.toHaveBeenCalled();
  });

  it('reconnects after the stream drops and refills the missed history', async () => {
    binanceHistory([110, 120]);
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();
    act(() => socket().open());

    act(() => socket().drop());
    expect(status()).toHaveTextContent('Reconnecting to Binance');

    await advance(999);
    expect(FakeWebSocket.instances).toHaveLength(1);
    await advance(1);
    expect(FakeWebSocket.instances).toHaveLength(2);

    act(() => socket().open());
    await flush();
    expect(status()).toHaveTextContent('Live · Binance');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('waits longer between repeated reconnect attempts', async () => {
    binanceHistory([110, 120]);
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();

    act(() => socket().drop());
    await advance(1_000);
    expect(FakeWebSocket.instances).toHaveLength(2);

    act(() => socket().drop());
    await advance(1_999);
    expect(FakeWebSocket.instances).toHaveLength(2);
    await advance(1);
    expect(FakeWebSocket.instances).toHaveLength(3);
  });

  it('falls back to the backend and polling when Binance is unreachable', async () => {
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ symbol: 'BTC/USDT', asset_type: 'crypto' }));
    expect(FakeWebSocket.instances).toHaveLength(0);
    expect(status()).toHaveTextContent('Live · updated');

    await advance(getRefreshIntervalMs('1h'));
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('never contacts Binance for stocks', async () => {
    render(<ChartPanel symbol="AAPL" />);
    await flush();
    await advance(getRefreshIntervalMs('1h'));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(FakeWebSocket.instances).toHaveLength(0);
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('closes the old stream and ignores its candles after switching timeframe', async () => {
    binanceHistory([110, 120]);
    render(<ChartPanel symbol="BTC/USDT" />);
    await flush();
    const first = socket();
    act(() => first.open());

    fireEvent.click(screen.getByText('1m'));
    await flush();

    expect(first.closed).toBe(true);
    expect(socket().url).toContain('btcusdt@kline_1m');
    act(() => first.emit({ e: 'kline', k: { t: START_MS + HOUR_MS, o: '1', h: '1', l: '1', c: '999' } }));
    expect(candleSeries(charts[charts.length - 1]).update).not.toHaveBeenCalled();
  });
});

describe('ChartPanel indicator panels', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    charts.length = 0;
    post.mockReset();
    setVisibility('visible');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // Enough candles for RSI(14), MACD(12/26/9) and ATR(14) to produce values.
  const longHistory = () => Array.from({ length: 60 }, (_, i) => ({
    timestamp: new Date(Date.UTC(2026, 9, 23, 0, i)).toISOString(),
    open: 100 + Math.sin(i / 3) * 5,
    high: 108 + Math.sin(i / 3) * 5,
    low: 95 + Math.sin(i / 3) * 5,
    close: 102 + Math.sin(i / 3) * 5,
  }));
  const liveSeries = () => charts[charts.length - 1].series.filter((series) => !series.removed);
  const inPane = (paneIndex: number) => liveSeries().filter((series) => series.paneIndex === paneIndex);
  const toggle = async (label: string) => {
    fireEvent.click(screen.getByRole('button', { name: label }));
    await flush();
  };

  it('keeps the price panel free of oscillators', async () => {
    post.mockResolvedValue({ data: longHistory() });
    render(<ChartPanel symbol="AAPL" />);
    await flush();
    await toggle('ATR 14');

    expect(inPane(1).map((series) => series.kind)).toEqual(['Line']);
    expect(inPane(0).every((series) => series.kind === 'Candlestick' || series.kind === 'Line')).toBe(true);
    expect(inPane(0)).toHaveLength(7);
  });

  it('draws RSI in its own panel with 70/30 guides and real values', async () => {
    post.mockResolvedValue({ data: longHistory() });
    render(<ChartPanel symbol="AAPL" />);
    await flush();
    await toggle('RSI 14');

    const [rsi] = inPane(1);
    expect(rsi.kind).toBe('Line');
    expect(rsi.priceLines).toEqual([70, 30]);
    const values = rsi.setData.mock.lastCall![0] as { value: number }[];
    expect(values.length).toBeGreaterThan(0);
    expect(values.every((point) => point.value >= 0 && point.value <= 100)).toBe(true);
  });

  it('draws MACD as line, signal and a coloured histogram in one panel', async () => {
    post.mockResolvedValue({ data: longHistory() });
    render(<ChartPanel symbol="AAPL" />);
    await flush();
    await toggle('MACD');

    expect(inPane(1).map((series) => series.kind).sort()).toEqual(['Histogram', 'Line', 'Line']);
    const histogram = inPane(1).find((series) => series.kind === 'Histogram')!;
    const bars = histogram.setData.mock.lastCall![0] as { value: number; color: string }[];
    expect(bars.length).toBeGreaterThan(0);
    for (const bar of bars) {
      expect(bar.color).toBe(bar.value >= 0 ? '#22c55e99' : '#ef444499');
    }
  });

  it('stacks panels in a fixed order and closes the gap when one is turned off', async () => {
    post.mockResolvedValue({ data: longHistory() });
    render(<ChartPanel symbol="AAPL" />);
    await flush();
    await toggle('RSI 14');
    await toggle('MACD');
    await toggle('ATR 14');

    expect(inPane(1)).toHaveLength(1);
    expect(inPane(2)).toHaveLength(3);
    expect(inPane(3)).toHaveLength(1);

    await toggle('RSI 14');
    expect(inPane(1).map((series) => series.kind).sort()).toEqual(['Histogram', 'Line', 'Line']);
    expect(inPane(2)).toHaveLength(1);
    expect(inPane(3)).toHaveLength(0);
  });

  it('rebuilds the panels on the new chart after a timeframe switch', async () => {
    post.mockResolvedValue({ data: longHistory() });
    render(<ChartPanel symbol="AAPL" />);
    await flush();
    await toggle('RSI 14');

    fireEvent.click(screen.getByText('1m'));
    await flush();

    expect(charts.length).toBeGreaterThan(1);
    const [rsi] = inPane(1);
    expect(rsi.kind).toBe('Line');
    expect(rsi.setData).toHaveBeenCalled();
  });
});

describe('ChartPanel symbol switch', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    charts.length = 0;
    post.mockReset();
    setVisibility('visible');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("never shows the previous symbol's price when the new symbol fails to load", async () => {
    post.mockResolvedValueOnce({ data: candles(2358.24) });
    const { rerender } = render(<ChartPanel symbol="ETH/USDT" />);
    await flush();
    expect(screen.getByTestId('last-price')).toHaveTextContent('2,358.24');

    post.mockRejectedValue(new Error('no data'));
    rerender(<ChartPanel symbol="AAPL" />);
    await flush();

    expect(screen.queryByTestId('last-price')).toBeNull();
    expect(screen.queryByTestId('day-change')).toBeNull();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});

describe('ChartPanel sentiment badge', () => {
  const get = vi.mocked(axios.get);

  beforeEach(() => {
    vi.useFakeTimers();
    charts.length = 0;
    post.mockReset();
    post.mockResolvedValue({ data: candles(105) });
    setVisibility('visible');
  });

  afterEach(() => {
    vi.useRealTimers();
    get.mockImplementation(() => Promise.resolve({ data: { sentiment_score: 0.5, sentiment_label: 'Neutral' } }));
  });

  it('says it needs AI instead of showing a score when no provider is set', async () => {
    get.mockResolvedValue({ data: { status: 'needs_ai', sentiment_score: null, sentiment_label: null, reason: 'No AI provider is configured.' } });
    render(<ChartPanel symbol="AAPL" />);
    await flush();

    const badge = screen.getByText('Sentiment needs AI');
    expect(badge.parentElement).toHaveAttribute('title', 'No AI provider is configured.');
    expect(screen.queryByText('+0.50')).toBeNull();
  });

  it('shows the score and label when the AI scored the headlines', async () => {
    get.mockResolvedValue({ data: { status: 'ok', sentiment_score: -0.35, sentiment_label: 'Bearish', reason: null } });
    render(<ChartPanel symbol="AAPL" />);
    await flush();

    expect(screen.getByText('Bearish')).toBeInTheDocument();
    expect(screen.getByText('-0.35')).toBeInTheDocument();
  });

  it('shows no number when sentiment cannot be loaded', async () => {
    get.mockRejectedValue(new Error('offline'));
    render(<ChartPanel symbol="AAPL" />);
    await flush();

    expect(screen.getByText('No sentiment')).toBeInTheDocument();
  });
});
