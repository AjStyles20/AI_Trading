export type CandlePoint = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type LinePoint = {
  time: number;
  value: number;
};

export type MacdPoint = {
  time: number;
  macd: number;
  signal: number;
  histogram: number;
};

const toLinePoints = (candles: CandlePoint[], values: Array<number | null>): LinePoint[] =>
  candles
    .map((candle, index) => {
      const value = values[index];
      if (value === null || value === undefined || Number.isNaN(value)) {
        return null;
      }

      return {
        time: candle.time,
        value,
      };
    })
    .filter((point): point is LinePoint => point !== null);

export const calculateSMA = (candles: CandlePoint[], period: number): LinePoint[] => {
  const values = candles.map((candle) => candle.close);
  const smaValues = values.map((_, index) => {
    if (index + 1 < period) {
      return null;
    }

    const window = values.slice(index + 1 - period, index + 1);
    return window.reduce((sum, value) => sum + value, 0) / period;
  });

  return toLinePoints(candles, smaValues);
};

export const calculateEMA = (candles: CandlePoint[], period: number): LinePoint[] => {
  const multiplier = 2 / (period + 1);
  let previousEma: number | null = null;

  const emaValues = candles.map((candle, index) => {
    if (index + 1 < period) {
      return null;
    }

    if (previousEma === null) {
      const seed = candles
        .slice(index + 1 - period, index + 1)
        .reduce((sum, item) => sum + item.close, 0) / period;
      previousEma = seed;
      return seed;
    }

    const next = (candle.close - previousEma) * multiplier + previousEma;
    previousEma = next;
    return next;
  });

  return toLinePoints(candles, emaValues);
};

export const calculateRSI = (candles: CandlePoint[], period: number): LinePoint[] => {
  if (candles.length <= period) {
    return [];
  }

  const closes = candles.map((candle) => candle.close);
  const gains: number[] = [];
  const losses: number[] = [];

  for (let index = 1; index < closes.length; index += 1) {
    const delta = closes[index] - closes[index - 1];
    gains.push(Math.max(delta, 0));
    losses.push(Math.max(-delta, 0));
  }

  let avgGain = gains.slice(0, period).reduce((sum, value) => sum + value, 0) / period;
  let avgLoss = losses.slice(0, period).reduce((sum, value) => sum + value, 0) / period;

  const rsiValues: Array<number | null> = Array(candles.length).fill(null);
  rsiValues[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);

  for (let index = period + 1; index < candles.length; index += 1) {
    const gain = gains[index - 1];
    const loss = losses[index - 1];
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    rsiValues[index] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }

  return toLinePoints(candles, rsiValues);
};

export const calculateMACD = (
  candles: CandlePoint[],
  fastPeriod = 12,
  slowPeriod = 26,
  signalPeriod = 9,
): MacdPoint[] => {
  const fast = calculateEMA(candles, fastPeriod);
  const slow = calculateEMA(candles, slowPeriod);
  const fastMap = new Map(fast.map((point) => [point.time, point.value]));
  const slowMap = new Map(slow.map((point) => [point.time, point.value]));

  const macdBase = candles
    .map((candle) => {
      const fastValue = fastMap.get(candle.time);
      const slowValue = slowMap.get(candle.time);

      if (fastValue === undefined || slowValue === undefined) {
        return null;
      }

      return {
        time: candle.time,
        value: fastValue - slowValue,
      };
    })
    .filter((point): point is LinePoint => point !== null);

  const signalSeed = macdBase.map((point) => ({
    time: point.time,
    open: point.value,
    high: point.value,
    low: point.value,
    close: point.value,
  }));

  const signal = calculateEMA(signalSeed, signalPeriod);
  const signalMap = new Map(signal.map((point) => [point.time, point.value]));

  return macdBase
    .map((point) => {
      const signalValue = signalMap.get(point.time);
      if (signalValue === undefined) {
        return null;
      }

      return {
        time: point.time,
        macd: point.value,
        signal: signalValue,
        histogram: point.value - signalValue,
      };
    })
    .filter((point): point is MacdPoint => point !== null);
};

export type BollingerPoint = {
  time: number;
  upper: number;
  middle: number;
  lower: number;
};

export const calculateBollingerBands = (candles: CandlePoint[], period = 20, stdDev = 2.0): BollingerPoint[] => {
  const sma = calculateSMA(candles, period);
  const smaMap = new Map(sma.map((p) => [p.time, p.value]));

  return candles
    .map((candle, index) => {
      const middle = smaMap.get(candle.time);
      if (middle === undefined || index + 1 < period) return null;

      const window = candles.slice(index + 1 - period, index + 1);
      const sumSq = window.reduce((acc, c) => acc + Math.pow(c.close - middle, 2), 0);
      const std = Math.sqrt(sumSq / period);

      return {
        time: candle.time,
        upper: middle + stdDev * std,
        middle: middle,
        lower: middle - stdDev * std,
      };
    })
    .filter((p): p is BollingerPoint => p !== null);
};

export const calculateATR = (candles: CandlePoint[], period = 14): LinePoint[] => {
  if (candles.length === 0) return [];
  const trueRanges: number[] = [candles[0].high - candles[0].low];

  for (let i = 1; i < candles.length; i++) {
    const high = candles[i].high;
    const low = candles[i].low;
    const prevClose = candles[i - 1].close;

    const tr = Math.max(
      high - low,
      Math.abs(high - prevClose),
      Math.abs(low - prevClose)
    );
    trueRanges.push(tr);
  }

  const atrValues: (number | null)[] = Array(candles.length).fill(null);

  if (candles.length <= period) return [];

  let sum = 0;
  for (let i = 1; i <= period; i++) {
    sum += trueRanges[i];
  }
  let currentATR = sum / period;
  atrValues[period] = currentATR;

  for (let i = period + 1; i < candles.length; i++) {
    currentATR = (currentATR * (period - 1) + trueRanges[i]) / period;
    atrValues[i] = currentATR;
  }

  return atrValues
    .map((value, index) => {
      if (value === null) return null;
      return { time: candles[index].time, value };
    })
    .filter((p): p is LinePoint => p !== null);
};
