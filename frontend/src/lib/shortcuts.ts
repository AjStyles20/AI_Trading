// Single-key shortcuts. They never fire while you type in a field or hold a
// modifier, so they can't steal text input or browser/OS shortcuts.

export const TIMEFRAME_KEYS: Record<string, string> = { '1': '1m', '2': '5m', '3': '15m', '4': '1h', '5': '4h', '6': '1D' };

export const INDICATOR_KEYS = { s: 'sma20', e: 'ema21', r: 'rsi14', m: 'macd', b: 'bb', a: 'atr' } as const;

export const SHORTCUTS: { keys: string; action: string }[] = [
  { keys: '1 – 6', action: 'Timeframe 1m, 5m, 15m, 1h, 4h, 1D' },
  { keys: 'S  E  R', action: 'Toggle SMA 20, EMA 21, RSI 14' },
  { keys: 'M  B  A', action: 'Toggle MACD, Bollinger Bands, ATR 14' },
  { keys: '/', action: 'Search the watchlist' },
  { keys: '?', action: 'Show or hide this list' },
  { keys: 'Esc', action: 'Close this list or the expanded chat' },
];

export const isShortcutEvent = (event: KeyboardEvent): boolean => {
  if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || event.repeat) return false;
  const target = event.target as HTMLElement | null;
  if (!target) return true;
  const tag = target.tagName;
  return !(tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable);
};
