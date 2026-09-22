import { useEffect, useRef, useState, useCallback } from 'react';
import axios from 'axios';
import { createChart, ColorType, CandlestickSeries, LineSeries, createSeriesMarkers } from 'lightweight-charts';
import type { CandlestickData, IChartApi, ISeriesApi, ISeriesMarkersPluginApi, LineData, SeriesMarker, Time, UTCTimestamp } from 'lightweight-charts';
import { calculateEMA, calculateMACD, calculateRSI, calculateSMA, calculateBollingerBands, calculateATR, type CandlePoint, type LinePoint, type MacdPoint } from '../lib/indicators';
import type { BacktestResults } from './BottomPanel';

const BACKEND_URL = 'http://127.0.0.1:8000';
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

  const [timeframe, setTimeframe] = useState('1h');
  const [isLoading, setIsLoading] = useState(false);
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

  const fetchChartData = useCallback(async () => {
    if (!seriesRef.current) return;
    setIsLoading(true);
    try {
      const assetType: AssetType = symbol.includes('/') || symbol.includes('-') ? 'crypto' : 'stock';
      const res = await axios.post(`${BACKEND_URL}/api/market/history`, {
        symbol,
        asset_type: assetType,
        interval: timeframe === '1D' ? '1d' : timeframe,
        limit: 500,
      });

      if (!res.data || !Array.isArray(res.data)) {
        console.warn('Invalid data format for', symbol);
        return;
      }

      const formattedData: ChartCandle[] = (res.data as HistoryPoint[]).map((point) => {
        const dateVal = point.timestamp || point.Date || point.date || point.index || point.Datetime;
        const timeVal = dateVal ? new Date(dateVal).getTime() : NaN;

        return {
          time: Math.floor(timeVal / 1000) as UTCTimestamp,
          open: Number(point.open || point.Open || 0),
          high: Number(point.high || point.High || 0),
          low: Number(point.low || point.Low || 0),
          close: Number(point.close || point.Close || 0),
        };
      })
        .filter((point) => !Number.isNaN(Number(point.time)))
        .sort((a, b) => Number(a.time) - Number(b.time));

      const uniqueData = formattedData.filter((point, index, values) => index === 0 || point.time !== values[index - 1].time);

      if (uniqueData.length > 0 && seriesRef.current) {
        seriesRef.current.setData(uniqueData);
        setCandleData(uniqueData as CandlePoint[]);
        chartRef.current?.timeScale().fitContent();
      }
    } catch (err) {
      console.error('Failed to fetch chart data:', err);
    } finally {
      setIsLoading(false);
    }
  }, [symbol, timeframe]);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0a0a0c' },
        textColor: '#9ca3af',
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
      atr: chart.addSeries(LineSeries, {
        color: '#fb923c',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        priceScaleId: 'left',
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
      chart.remove();
    };
  }, [fetchChartData]);

  useEffect(() => {
    const smaSeries = overlaySeriesRef.current.sma20;
    const emaSeries = overlaySeriesRef.current.ema21;
    const bbUpperSeries = overlaySeriesRef.current.bbUpper;
    const bbMidSeries = overlaySeriesRef.current.bbMid;
    const bbLowerSeries = overlaySeriesRef.current.bbLower;
    const atrSeries = overlaySeriesRef.current.atr;
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
    if (atrSeries) {
      atrSeries.setData(enabledIndicators.atr ? toChartLineData(calculateATR(candleData, 14)) : []);
    }

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
  const timeframes = ['1m', '5m', '15m', '1h', '4h', '1D'];

  const toggleIndicator = (key: IndicatorKey) => {
    setEnabledIndicators((current) => ({
      ...current,
      [key]: !current[key],
    }));
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#121216]">
      <div className="flex items-center justify-between pb-3 border-b border-[#2a2a35] flex-shrink-0">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
            <h2 className="text-lg font-bold text-white tracking-widest uppercase">{symbol}</h2>
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
        {isLoading && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/40 backdrop-blur-[2px] rounded-xl">
            <div className="flex flex-col items-center gap-2">
              <div className="w-8 h-8 border-4 border-[#a55eea] border-t-transparent rounded-full animate-spin"></div>
              <span className="text-[10px] text-white font-bold tracking-widest uppercase">Syncing Price Data...</span>
            </div>
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
