import type { CandlePoint } from './indicators';

export type PriceDirection = 'up' | 'down' | 'flat';

const SECONDS_PER_DAY = 86_400;

const largeFormatter = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const smallFormatter = new Intl.NumberFormat('en-US', { maximumSignificantDigits: 4 });
const largeSigned = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'exceptZero' });
const smallSigned = new Intl.NumberFormat('en-US', { maximumSignificantDigits: 4, signDisplay: 'exceptZero' });

// Two decimals with thousands separators for normal prices; significant digits
// for sub-1 prices so small coins do not collapse to 0.00.
export const formatPrice = (value: number, { signed = false }: { signed?: boolean } = {}): string => {
  const small = Math.abs(value) < 1 && value !== 0;
  if (signed) return (small ? smallSigned : largeSigned).format(value);
  return (small ? smallFormatter : largeFormatter).format(value);
};

export const getPriceDirection = (previous: number | null, next: number): PriceDirection => {
  if (previous === null || next === previous) return 'flat';
  return next > previous ? 'up' : 'down';
};

// Change from the close of the candle at (or just before) 24 hours before the
// latest candle. Returns null when the loaded history does not reach back 24 h.
export const get24hChange = (candles: CandlePoint[]): { change: number; percent: number } | null => {
  const latest = candles[candles.length - 1];
  if (!latest) return null;
  const target = latest.time - SECONDS_PER_DAY;
  for (let i = candles.length - 2; i >= 0; i -= 1) {
    if (candles[i].time <= target) {
      const reference = candles[i].close;
      if (!(reference > 0)) return null;
      const change = latest.close - reference;
      return { change, percent: (change / reference) * 100 };
    }
  }
  return null;
};
