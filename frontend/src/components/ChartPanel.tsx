import { useEffect, useRef, useState, useCallback } from 'react';
import axios from 'axios';
import { createChart, ColorType, CandlestickSeries, HistogramSeries, LineSeries, createSeriesMarkers } from 'lightweight-charts';
import type { CandlestickData, IChartApi, ISeriesApi, ISeriesMarkersPluginApi, LineData, SeriesMarker, SeriesType, Time, UTCTimestamp } from 'lightweight-charts';
import { calculateEMA, calculateMACD, calculateRSI, calculateSMA, calculateBollingerBands, calculateATR, type CandlePoint, type LinePoint, type MacdPoint } from '../lib/indicators';
import type { BacktestResults } from './BottomPanel';
import { BACKEND_URL } from '../lib/api';
import { getHistoryLimit, getRefreshIntervalMs, INITIAL_VISIBLE_CANDLES } from '../lib/liveRefresh';
import { formatPrice, get24hChange, getPriceDirection, type PriceDirection } from '../lib/priceTicker';
import {
  binanceStreamUrl,
  fetchBinanceKlines,
  mergeLiveCandle,
  parseStreamMessage,
  RECONNECT_DELAYS_MS,
  toBinanceInterval,
  toBinanceSymbol,
  type LiveTicker,
} from '../lib/binanceMarket';

type IndicatorKey = 'sma20' | 'ema21' | 'rsi14' | 'macd' | 'bb' | 'atr';
type AssetType = 'crypto' | 'stock';

type HistoryPoint = {
  timestamp?: string;
  Date?: string;
  date?: string;
  index?: string;
  Datetime?: string;
  open?: number | string;
  Open?: number | string;
  high?: number | string;
  High?: number | string;
  low?: number | string;
  Low?: number | string;
  close?: number | string;
  Close?: number | string;
};

type ChartCandle = CandlestickData<Time>;
type ChartLine = LineData<Time>;
type ChartMarker = SeriesMarker<Time>;

// Where the chart's data comes from: Binance (history + live stream) for crypto
// pairs it lists, otherwise the backend (Yahoo Finance) refreshed on a timer.
type DataSource = 'binance' | 'backend';

// Oscillators drawn in their own panels below the price chart.
type IndicatorPanes = {
  rsi?: ISeriesApi<'Line'>;
  macd?: { line: ISeriesApi<'Line'>; signal: ISeriesApi<'Line'>; histogram: ISeriesApi<'Histogram'> };
  atr?: ISeriesApi<'Line'>;
};
// Share of the chart height: price panel vs each indicator panel.
const PRICE_PANE_STRETCH = 3;
const INDICATOR_PANE_STRETCH = 1;
type StreamStatus = 'connecting' | 'live' | 'reconnecting';

const PRICE_FLASH_MS = 500;
// Upper bound on candles kept while live candles are appended.
const MAX_LIVE_CANDLES = 2_000;

const toChartCandles = (candles: CandlePoint[]): ChartCandle[] =>
  candles.map((candle) => ({ ...candle, time: candle.time as UTCTimestamp }));

const normalizeBackendHistory = (points: HistoryPoint[]): CandlePoint[] => {
  const candles = points.map((point) => {
    const dateVal = point.timestamp || point.Date || point.date || point.index || point.Datetime;
    const timeVal = dateVal ? new Date(dateVal).getTime() : NaN;
    return {
      time: Math.floor(timeVal / 1000),
      open: Number(point.open || point.Open || 0),
      high: Number(point.high || point.High || 0),
      low: Number(point.low || point.Low || 0),
      close: Number(point.close || point.Close || 0),
    };
  })
    .filter((point) => !Number.isNaN(point.time))
    .sort((a, b) => a.time - b.time);
  return candles.filter((point, index, values) => index === 0 || point.time !== values[index - 1].time);
};

export default function ChartPanel({
  symbol,
  backtestResults,
}: {
  symbol: string,
  backtestResults?: BacktestResults
}) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const overlaySeriesRef = useRef<Record<string, ISeriesApi<'Line'>>>({});
  const indicatorPanesRef = useRef<IndicatorPanes>({});
  // Each fetch takes a new id; a response is applied only if its id is still the
  // latest, so a slow reply for a previous symbol/timeframe or a disposed chart
  // is discarded.
  const requestIdRef = useRef(0);
  const inFlightRef = useRef(false);
  const lastPriceRef = useRef<number | null>(null);
  const flashTimerRef = useRef<number | undefined>(undefined);
  // The Binance stream key ("BTCUSDT:1m") whose history is on the chart. Live
  // candles are applied only on top of their own market's history.
  const historyKeyRef = useRef<string | null>(null);

  const [timeframe, setTimeframe] = useState('1h');
  const [isLoading, setIsLoading] = useState(false);
  const [dataError, setDataError] = useState('');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [refreshFailed, setRefreshFailed] = useState(false);
  const [priceDirection, setPriceDirection] = useState<PriceDirection>('flat');
  const [priceFlash, setPriceFlash] = useState<PriceDirection>('flat');
  const [dataSource, setDataSource] = useState<DataSource | null>(null);
  // Stream status and ticker are stored with the stream key they belong to, so
  // a switch to another symbol/timeframe never shows the previous market's state.
  const [streamState, setStreamState] = useState<{ key: string; status: StreamStatus } | null>(null);
  const [tickerState, setTickerState] = useState<{ key: string; ticker: LiveTicker } | null>(null);
  const [sentiment, setSentiment] = useState<{ score: number, label: string } | null>(null);
  const [candleData, setCandleData] = useState<CandlePoint[]>([]);
  const [enabledIndicators, setEnabledIndicators] = useState<Record<IndicatorKey, boolean>>({
    sma20: true,
    ema21: true,
    rsi14: false,
    macd: false,
    bb: false,
    atr: false,
  });

  // A background fetch is a live refresh: no loading overlay, no view reset, and
  // a failure keeps the last good chart instead of replacing it with an error.
  const fetchChartData = useCallback(async ({ background = false }: { background?: boolean } = {}) => {
    if (!seriesRef.current) return;
    if (background && inFlightRef.current) return;
    const requestId = ++requestIdRef.current;
    inFlightRef.current = true;
    if (!background) {
      setIsLoading(true);
      setDataError('');
    }
    try {
      // Crypto pairs Binance lists come straight from Binance, matching the live
      // stream. Anything else, or Binance being unreachable, uses the backend.
      const binanceSymbol = toBinanceSymbol(symbol);
      const binanceInterval = toBinanceInterval(timeframe);
      let history: CandlePoint[] | null = null;
      let source: DataSource = 'backend';
      if (binanceSymbol && binanceInterval) {
        try {
          history = await fetchBinanceKlines(binanceSymbol, binanceInterval, getHistoryLimit(timeframe));
          source = 'binance';
        } catch (err) {
          console.warn(`Binance history unavailable for ${binanceSymbol}; using the backend instead:`, err);
        }
        if (requestId !== requestIdRef.current) return;
      }

      if (!history) {
        const assetType: AssetType = symbol.includes('/') || symbol.includes('-') ? 'crypto' : 'stock';
        const res = await axios.post(`${BACKEND_URL}/api/market/history`, {
          symbol,
          asset_type: assetType,
          interval: timeframe === '1D' ? '1d' : timeframe,
          limit: getHistoryLimit(timeframe),
        });
        if (requestId !== requestIdRef.current) return;

        if (!res.data || !Array.isArray(res.data)) {
          console.warn('Invalid data format for', symbol);
          if (background) setRefreshFailed(true);
          else setDataError('The data provider returned an invalid response.');
          return;
        }
        history = normalizeBackendHistory(res.data as HistoryPoint[]);
      }

      const uniqueData = toChartCandles(history);

      if (uniqueData.length > 0 && seriesRef.current) {
        seriesRef.current.setData(uniqueData);
        setCandleData(history);
        setDataSource(source);
        historyKeyRef.current = source === 'binance' ? `${binanceSymbol}:${binanceInterval}` : null;
        // Colour the price by the direction of the last live move. A fresh load
        // (new symbol/timeframe) starts neutral rather than comparing against
        // another market's price.
        const latestClose = uniqueData[uniqueData.length - 1].close;
        const direction = background ? getPriceDirection(lastPriceRef.current, latestClose) : 'flat';
        lastPriceRef.current = latestClose;
        window.clearTimeout(flashTimerRef.current);
        if (!background) {
          setPriceDirection('flat');
          setPriceFlash('flat');
        } else if (direction !== 'flat') {
          setPriceDirection(direction);
          setPriceFlash(direction);
          flashTimerRef.current = window.setTimeout(() => setPriceFlash('flat'), PRICE_FLASH_MS);
        }
        if (!background) {
          // Open on the recent candles rather than squeezing the whole history
          // into view; older candles are a drag away.
          const timeScale = chartRef.current?.timeScale();
          if (uniqueData.length > INITIAL_VISIBLE_CANDLES) {
            timeScale?.setVisibleLogicalRange({ from: uniqueData.length - INITIAL_VISIBLE_CANDLES, to: uniqueData.length + 2 });
          } else {
            timeScale?.fitContent();
          }
        }
        setLastUpdated(new Date());
        setRefreshFailed(false);
      } else if (background) {
        setRefreshFailed(true);
      } else {
        setDataError('No price history was returned for this symbol and interval.');
      }
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      if (background) {
        console.warn('Live chart refresh failed:', err);
        setRefreshFailed(true);
      } else {
        console.error('Failed to fetch chart data:', err);
        setDataError(axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail : 'Could not load price history. Check your connection and retry.');
      }
    } finally {
      if (requestId === requestIdRef.current) {
        inFlightRef.current = false;
        if (!background) setIsLoading(false);
      }
    }
  }, [symbol, timeframe]);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0a0a0c' },
        textColor: '#9ca3af',
        panes: { separatorColor: '#2a2a35', separatorHoverColor: '#3a3a48', enableResize: true },
      },
      grid: {
        vertLines: { color: '#2a2a35' },
        horzLines: { color: '#2a2a35' },
      },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      timeScale: {
        borderColor: '#2a2a35',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });

    chartRef.current = chart;
    seriesRef.current = candlestickSeries;
    markersRef.current = createSeriesMarkers(candlestickSeries);
    overlaySeriesRef.current = {
      sma20: chart.addSeries(LineSeries, {
        color: '#f59e0b',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      }),
      ema21: chart.addSeries(LineSeries, {
        color: '#38bdf8',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      }),
      bbUpper: chart.addSeries(LineSeries, {
        color: '#a78bfa',
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      }),
      bbMid: chart.addSeries(LineSeries, {
        color: '#c084fc',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      }),
      bbLower: chart.addSeries(LineSeries, {
        color: '#a78bfa',
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      }),
      equityCurve: chart.addSeries(LineSeries, {
        color: '#22c55e',
        lineWidth: 2,
        priceLineVisible: true,
        lastValueVisible: true,
        priceScaleId: 'left',
      }),
    };

    fetchChartData();

    // The chart zooms on every mouse wheel event, which traps the page: with the
    // pointer over the chart the user cannot scroll back up. Let the plain wheel
    // scroll the page and keep chart zoom on Ctrl/Cmd + wheel (also what a
    // touchpad pinch sends). Stopping the event while it travels down to the
    // chart leaves the browser's default page scroll intact.
    const container = chartContainerRef.current;
    const passWheelToPage = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) event.stopPropagation();
    };
    container.addEventListener('wheel', passWheelToPage, { capture: true });

    const handleResize = () => {
      if (chartContainerRef.current && chart) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      container.removeEventListener('wheel', passWheelToPage, { capture: true });
      // Invalidate any in-flight fetch so it cannot write to the removed chart.
      requestIdRef.current += 1;
      inFlightRef.current = false;
      window.clearTimeout(flashTimerRef.current);
      chart.remove();
    };
  }, [fetchChartData]);

  const showPriceMove = useCallback((price: number) => {
    const direction = getPriceDirection(lastPriceRef.current, price);
    lastPriceRef.current = price;
    if (direction === 'flat') return;
    window.clearTimeout(flashTimerRef.current);
    setPriceDirection(direction);
    setPriceFlash(direction);
    flashTimerRef.current = window.setTimeout(() => setPriceFlash('flat'), PRICE_FLASH_MS);
  }, []);

  const applyLiveCandle = useCallback((key: string, candle: CandlePoint) => {
    if (historyKeyRef.current !== key || !seriesRef.current) return;
    try {
      seriesRef.current.update({ ...candle, time: candle.time as UTCTimestamp });
    } catch (err) {
      // The chart rejects candles older than its last bar; nothing to apply.
      console.warn('Ignored out-of-order live candle:', err);
      return;
    }
    setCandleData((current) => mergeLiveCandle(current, candle, MAX_LIVE_CANDLES));
    setLastUpdated(new Date());
    setRefreshFailed(false);
  }, []);

  const applyTicker = useCallback((key: string, ticker: LiveTicker) => {
    setTickerState({ key, ticker });
    showPriceMove(ticker.price);
  }, [showPriceMove]);

  // Live Binance stream: the forming candle (~every 2 s) and the 24h ticker
  // (~every 1 s). Reconnects with increasing delays, and refetches history after
  // a reconnect to fill the gap.
  useEffect(() => {
    const binanceSymbol = toBinanceSymbol(symbol);
    const interval = toBinanceInterval(timeframe);
    if (dataSource !== 'binance' || !binanceSymbol || !interval) return;
    const key = `${binanceSymbol}:${interval}`;
    let socket: WebSocket | null = null;
    let disposed = false;
    let attempt = 0;
    let retryTimer: number | undefined;

    const connect = () => {
      const current = new WebSocket(binanceStreamUrl(binanceSymbol, interval));
      socket = current;
      current.onopen = () => {
        if (disposed) return;
        const recovering = attempt > 0;
        attempt = 0;
        setStreamState({ key, status: 'live' });
        if (recovering) void fetchChartData({ background: true });
      };
      current.onmessage = (event: MessageEvent) => {
        if (disposed) return;
        const message = parseStreamMessage(String(event.data));
        if (message?.kind === 'kline') applyLiveCandle(key, message.candle);
        else if (message?.kind === 'ticker') applyTicker(key, message.ticker);
      };
      current.onclose = () => {
        if (disposed) return;
        setStreamState({ key, status: 'reconnecting' });
        const delay = RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)];
        attempt += 1;
        retryTimer = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      disposed = true;
      window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, [dataSource, symbol, timeframe, fetchChartData, applyLiveCandle, applyTicker]);

  useEffect(() => {
    // Streamed markets update themselves; only backend-sourced charts poll.
    if (dataSource === 'binance') return;
    const refresh = () => {
      if (document.visibilityState === 'visible') void fetchChartData({ background: true });
    };
    const intervalId = window.setInterval(refresh, getRefreshIntervalMs(timeframe));
    // Hidden tabs skip refreshes; catch up as soon as the tab is shown again.
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [dataSource, fetchChartData, timeframe]);

  // RSI, MACD and ATR each get a panel below the price chart, in that order.
  // Toggling rebuilds them so the remaining panels close up. fetchChartData
  // changes whenever the chart itself is rebuilt (new symbol or timeframe), so
  // the panels are recreated on the new chart too.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const created: ISeriesApi<SeriesType>[] = [];
    const panes: IndicatorPanes = {};
    let paneIndex = 1;

    if (enabledIndicators.rsi14) {
      const rsi = chart.addSeries(LineSeries, { color: '#34d399', lineWidth: 2, priceLineVisible: false }, paneIndex);
      // Conventional overbought / oversold guides.
      rsi.createPriceLine({ price: 70, color: '#ef444480', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' });
      rsi.createPriceLine({ price: 30, color: '#22c55e80', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '' });
      panes.rsi = rsi;
      created.push(rsi);
      paneIndex += 1;
    }
    if (enabledIndicators.macd) {
      const histogram = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, paneIndex);
      const line = chart.addSeries(LineSeries, { color: '#e879f9', lineWidth: 2, priceLineVisible: false }, paneIndex);
      const signal = chart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1, priceLineVisible: false }, paneIndex);
      panes.macd = { line, signal, histogram };
      created.push(histogram, line, signal);
      paneIndex += 1;
    }
    if (enabledIndicators.atr) {
      const atr = chart.addSeries(LineSeries, { color: '#fb923c', lineWidth: 2, priceLineVisible: false }, paneIndex);
      panes.atr = atr;
      created.push(atr);
    }

    const allPanes = chart.panes();
    allPanes[0]?.setStretchFactor(PRICE_PANE_STRETCH);
    allPanes.slice(1).forEach((pane) => pane.setStretchFactor(INDICATOR_PANE_STRETCH));
    indicatorPanesRef.current = panes;

    return () => {
      indicatorPanesRef.current = {};
      try {
        created.forEach((series) => chart.removeSeries(series));
        while (chart.panes().length > 1) chart.removePane(chart.panes().length - 1);
      } catch {
        // The chart was already removed (symbol or timeframe switch).
      }
    };
  }, [fetchChartData, enabledIndicators.rsi14, enabledIndicators.macd, enabledIndicators.atr]);

  useEffect(() => {
    const smaSeries = overlaySeriesRef.current.sma20;
    const emaSeries = overlaySeriesRef.current.ema21;
    const bbUpperSeries = overlaySeriesRef.current.bbUpper;
    const bbMidSeries = overlaySeriesRef.current.bbMid;
    const bbLowerSeries = overlaySeriesRef.current.bbLower;
    const equityCurveSeries = overlaySeriesRef.current.equityCurve;

    const toChartLineData = (points: LinePoint[]): ChartLine[] =>
      points.map((point) => ({
        time: point.time as UTCTimestamp,
        value: point.value,
      }));

    if (smaSeries) {
      smaSeries.setData(enabledIndicators.sma20 ? toChartLineData(calculateSMA(candleData, 20)) : []);
    }
    if (emaSeries) {
      emaSeries.setData(enabledIndicators.ema21 ? toChartLineData(calculateEMA(candleData, 21)) : []);
    }
    if (bbUpperSeries && bbMidSeries && bbLowerSeries) {
      if (enabledIndicators.bb) {
        const bb = calculateBollingerBands(candleData, 20, 2.0);
        bbUpperSeries.setData(bb.map(b => ({ time: b.time as UTCTimestamp, value: b.upper })));
        bbMidSeries.setData(bb.map(b => ({ time: b.time as UTCTimestamp, value: b.middle })));
        bbLowerSeries.setData(bb.map(b => ({ time: b.time as UTCTimestamp, value: b.lower })));
      } else {
        bbUpperSeries.setData([]);
        bbMidSeries.setData([]);
        bbLowerSeries.setData([]);
      }
    }
    const panes = indicatorPanesRef.current;
    panes.rsi?.setData(toChartLineData(calculateRSI(candleData, 14)));
    if (panes.macd) {
      const macd = calculateMACD(candleData);
      panes.macd.line.setData(macd.map((point) => ({ time: point.time as UTCTimestamp, value: point.macd })));
      panes.macd.signal.setData(macd.map((point) => ({ time: point.time as UTCTimestamp, value: point.signal })));
      panes.macd.histogram.setData(macd.map((point) => ({
        time: point.time as UTCTimestamp,
        value: point.histogram,
        color: point.histogram >= 0 ? '#22c55e99' : '#ef444499',
      })));
    }
    panes.atr?.setData(toChartLineData(calculateATR(candleData, 14)));

    if (equityCurveSeries && backtestResults?.equity_curve && candleData.length > 0) {
      const eqData = backtestResults.equity_curve.slice(1);
      if (eqData.length === candleData.length) {
        equityCurveSeries.setData(candleData.map((c, i) => ({ time: c.time as UTCTimestamp, value: eqData[i] })));
      } else {
        equityCurveSeries.setData([]);
      }
    } else if (equityCurveSeries) {
      equityCurveSeries.setData([]);
    }
  }, [candleData, enabledIndicators, backtestResults]);

  useEffect(() => {
    const fetchSentiment = async () => {
      try {
        const querySymbol = symbol.replace('/', '-');
        const res = await axios.get(`${BACKEND_URL}/api/research/sentiment/${querySymbol}`);
        setSentiment({ score: res.data.sentiment_score, label: res.data.sentiment_label });
      } catch (err) {
        console.error('Failed to fetch sentiment:', err);
      }
    };
    fetchSentiment();
  }, [symbol]);

  useEffect(() => {
    if (!markersRef.current) return;

    if (!backtestResults || !backtestResults.trade_history) {
      markersRef.current.setMarkers([]);
      return;
    }

    const markers: ChartMarker[] = backtestResults.trade_history.map((trade) => ({
      time: Math.floor(new Date(trade.timestamp).getTime() / 1000) as UTCTimestamp,
      position: trade.type === 'BUY' ? 'belowBar' : 'aboveBar',
      color: trade.type === 'BUY' ? '#22c55e' : '#ef4444',
      shape: trade.type === 'BUY' ? 'arrowUp' : 'arrowDown',
      text: trade.type,
      size: 1.5,
    }));

    markers.sort((left, right) => Number(left.time) - Number(right.time));
    markersRef.current.setMarkers(markers);
  }, [backtestResults, timeframe, symbol]);

  const rsiData = calculateRSI(candleData, 14);
  const macdData = calculateMACD(candleData);
  const latestRsi = rsiData[rsiData.length - 1]?.value ?? null;
  const latestMacd: MacdPoint | null = macdData[macdData.length - 1] ?? null;
  const binanceSymbol = toBinanceSymbol(symbol);
  const binanceInterval = toBinanceInterval(timeframe);
  const streamKey = binanceSymbol && binanceInterval ? `${binanceSymbol}:${binanceInterval}` : null;
  const streaming = dataSource === 'binance' && streamKey !== null;
  const streamStatus: StreamStatus | null = streaming
    ? (streamState?.key === streamKey ? streamState.status : 'connecting')
    : null;
  const liveTicker = streaming && tickerState?.key === streamKey ? tickerState.ticker : null;
  // The ticker carries the exchange's own last price and 24h change; without it
  // fall back to the loaded candles.
  const latestPrice = liveTicker?.price ?? candleData[candleData.length - 1]?.close ?? null;
  const dayChange = liveTicker ? { change: liveTicker.change, percent: liveTicker.percent } : get24hChange(candleData);
  const statusDot = streaming
    ? (streamStatus === 'live' ? 'bg-green-500 animate-pulse' : streamStatus === 'reconnecting' ? 'bg-amber-500' : 'bg-gray-600')
    : (refreshFailed ? 'bg-amber-500' : lastUpdated ? 'bg-green-500 animate-pulse' : 'bg-gray-600');
  const sourceTitle = streaming
    ? `Streaming ${binanceSymbol} live from Binance (data-stream.binance.vision); the price updates about every second.`
    : `Refreshes every ${getRefreshIntervalMs(timeframe) / 1000}s from Yahoo Finance via the backend; prices can lag the exchange.`;
  const timeframes = ['1m', '5m', '15m', '1h', '4h', '1D'];

  const toggleIndicator = (key: IndicatorKey) => {
    setEnabledIndicators((current) => ({
      ...current,
      [key]: !current[key],
    }));
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#121216] pt-3">
      <div className="flex items-center justify-between pb-3 border-b border-[#2a2a35] flex-shrink-0">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2" title={sourceTitle}>
            <div className={`w-2 h-2 rounded-full ${statusDot}`}></div>
            <h2 className="text-lg font-bold text-white tracking-widest uppercase">{symbol}</h2>
            {latestPrice !== null && (
              <div className="flex items-baseline gap-2">
                <span
                  data-testid="last-price"
                  data-direction={priceDirection}
                  className={`text-lg font-bold tabular-nums px-1.5 rounded transition-colors duration-500 ${
                    priceDirection === 'up' ? 'text-green-400' : priceDirection === 'down' ? 'text-red-400' : 'text-white'
                  } ${priceFlash === 'up' ? 'bg-green-500/25' : priceFlash === 'down' ? 'bg-red-500/25' : 'bg-transparent'}`}
                >
                  {formatPrice(latestPrice)}
                </span>
                {dayChange && (
                  <span
                    data-testid="day-change"
                    title="Change over the last 24 hours"
                    className={`text-xs font-semibold tabular-nums ${
                      dayChange.change > 0 ? 'text-green-400' : dayChange.change < 0 ? 'text-red-400' : 'text-gray-400'
                    }`}
                  >
                    {formatPrice(dayChange.change, { signed: true })} ({dayChange.percent > 0 ? '+' : ''}{dayChange.percent.toFixed(2)}%) 24h
                  </span>
                )}
              </div>
            )}
            {streaming ? (
              <span data-testid="live-status" className={`text-[10px] ${streamStatus === 'reconnecting' ? 'text-amber-400' : 'text-gray-500'}`}>
                {streamStatus === 'live' ? 'Live · Binance' : streamStatus === 'reconnecting' ? 'Reconnecting to Binance…' : 'Connecting to Binance…'}
              </span>
            ) : lastUpdated && (
              <span data-testid="live-status" className={`text-[10px] ${refreshFailed ? 'text-amber-400' : 'text-gray-500'}`}>
                {refreshFailed ? 'Update failed · last' : 'Live · updated'} {lastUpdated.toLocaleTimeString()}
              </span>
            )}
          </div>
          <div className="flex gap-1 bg-[#1c1c24] p-1 rounded-lg border border-[#2a2a35]">
            {timeframes.map((tf) => (
              <button
                key={tf}
                id={`tf-${tf}`}
                onClick={() => setTimeframe(tf)}
                className={`px-3 py-1.5 text-[10px] font-bold rounded transition-all min-w-[32px] ${
                  timeframe === tf
                    ? 'bg-[#a55eea] text-white shadow-lg'
                    : 'text-gray-500 hover:text-white hover:bg-[#2a2a35]'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>
        <div className="flex gap-2 text-sm text-gray-400 items-center">
          {sentiment && (
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#2a2a35] bg-[#1c1c24] ${sentiment.score > 0 ? 'text-green-500 border-green-500/30' : sentiment.score < 0 ? 'text-red-500 border-red-500/30' : 'text-gray-400'}`} title="AI Market Sentiment">
              <span className="text-[10px] uppercase font-bold tracking-wider">{sentiment.label}</span>
              <span className="text-xs font-bold">{sentiment.score > 0 ? '+' : ''}{sentiment.score.toFixed(2)}</span>
            </div>
          )}
          <button onClick={() => toggleIndicator('sma20')} className={`px-3 py-1.5 rounded-lg border transition-all text-xs font-semibold ${enabledIndicators.sma20 ? 'bg-amber-500/10 border-amber-500 text-amber-300' : 'bg-[#1c1c24] border-[#2a2a35] hover:border-amber-500/40'}`}>
            SMA 20
          </button>
          <button onClick={() => toggleIndicator('ema21')} className={`px-3 py-1.5 rounded-lg border transition-all text-xs font-semibold ${enabledIndicators.ema21 ? 'bg-sky-500/10 border-sky-500 text-sky-300' : 'bg-[#1c1c24] border-[#2a2a35] hover:border-sky-500/40'}`}>
            EMA 21
          </button>
          <button onClick={() => toggleIndicator('rsi14')} className={`px-3 py-1.5 rounded-lg border transition-all text-xs font-semibold ${enabledIndicators.rsi14 ? 'bg-emerald-500/10 border-emerald-500 text-emerald-300' : 'bg-[#1c1c24] border-[#2a2a35] hover:border-emerald-500/40'}`}>
            RSI 14
          </button>
          <button onClick={() => toggleIndicator('macd')} className={`px-3 py-1.5 rounded-lg border transition-all text-xs font-semibold ${enabledIndicators.macd ? 'bg-fuchsia-500/10 border-fuchsia-500 text-fuchsia-300' : 'bg-[#1c1c24] border-[#2a2a35] hover:border-fuchsia-500/40'}`}>
            MACD
          </button>
          <button onClick={() => toggleIndicator('bb')} className={`px-3 py-1.5 rounded-lg border transition-all text-xs font-semibold ${enabledIndicators.bb ? 'bg-purple-500/10 border-purple-500 text-purple-300' : 'bg-[#1c1c24] border-[#2a2a35] hover:border-purple-500/40'}`}>
            BB 20
          </button>
          <button onClick={() => toggleIndicator('atr')} className={`px-3 py-1.5 rounded-lg border transition-all text-xs font-semibold ${enabledIndicators.atr ? 'bg-orange-500/10 border-orange-500 text-orange-300' : 'bg-[#1c1c24] border-[#2a2a35] hover:border-orange-500/40'}`}>
            ATR 14
          </button>
        </div>
      </div>

      <div className="flex-1 w-full mt-3 relative group">
        <div
          ref={chartContainerRef}
          className="absolute inset-0 bg-[#0a0a0c] rounded-xl border border-[#2a2a35] overflow-hidden"
        />
        <div className="pointer-events-none absolute top-2 left-3 z-10 text-[10px] text-gray-600">
          Ctrl + scroll to zoom · drag to pan
        </div>
        {isLoading && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/40 backdrop-blur-[2px] rounded-xl">
            <div className="flex flex-col items-center gap-2">
              <div className="w-8 h-8 border-4 border-[#a55eea] border-t-transparent rounded-full animate-spin"></div>
              <span className="text-[10px] text-white font-bold tracking-widest uppercase">Syncing Price Data...</span>
            </div>
          </div>
        )}
        {!isLoading && dataError && (
          <div role="alert" className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-[#0a0a0c]/90 rounded-xl p-6 text-center">
            <p className="text-sm text-amber-300">{dataError}</p>
            <button onClick={() => void fetchChartData()} className="px-3 py-2 bg-[#a55eea] text-white rounded-lg text-xs">Retry price data</button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
        <div className="rounded-xl border border-[#2a2a35] bg-[#0d0d11] px-3 py-2">
          <div className="text-[10px] uppercase tracking-widest text-gray-500">Indicators</div>
          <div className="text-xs text-white mt-1">
            {[enabledIndicators.sma20 && 'SMA 20', enabledIndicators.ema21 && 'EMA 21', enabledIndicators.rsi14 && 'RSI 14', enabledIndicators.macd && 'MACD', enabledIndicators.bb && 'BB 20', enabledIndicators.atr && 'ATR 14'].filter(Boolean).join(' · ') || 'None enabled'}
          </div>
        </div>
        <div className="rounded-xl border border-[#2a2a35] bg-[#0d0d11] px-3 py-2">
          <div className="text-[10px] uppercase tracking-widest text-gray-500">RSI Snapshot</div>
          <div className={`text-sm font-bold mt-1 ${latestRsi !== null && latestRsi >= 70 ? 'text-red-400' : latestRsi !== null && latestRsi <= 30 ? 'text-green-400' : 'text-white'}`}>
            {latestRsi !== null ? latestRsi.toFixed(2) : '--'}
          </div>
        </div>
        <div className="rounded-xl border border-[#2a2a35] bg-[#0d0d11] px-3 py-2">
          <div className="text-[10px] uppercase tracking-widest text-gray-500">MACD Bias</div>
          <div className={`text-sm font-bold mt-1 ${latestMacd && latestMacd.histogram >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {latestMacd ? `${latestMacd.histogram >= 0 ? 'Bullish' : 'Bearish'} ${latestMacd.histogram.toFixed(3)}` : '--'}
          </div>
        </div>
        <div className="rounded-xl border border-[#2a2a35] bg-[#0d0d11] px-3 py-2">
          <div className="text-[10px] uppercase tracking-widest text-gray-500">What-If Ready</div>
          <div className="text-xs text-white mt-1">Use the bottom panel to vary interval, capital, fees, and slippage.</div>
        </div>
      </div>
    </div>
  );
}
