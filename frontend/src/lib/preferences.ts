// Per-browser UI preferences. Every read is validated: anything missing,
// corrupt or from an older version falls back to the default.

export const PREF_KEYS = {
  symbol: 'astral.chart.symbol',
  timeframe: 'astral.chart.timeframe',
  indicators: 'astral.chart.indicators',
} as const;

export const readPreference = <T>(key: string, parse: (value: unknown) => T | null, fallback: T): T => {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return fallback;
    return parse(JSON.parse(raw)) ?? fallback;
  } catch {
    return fallback;
  }
};

export const storePreference = (key: string, value: unknown) => {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage unavailable (private window); the choice still applies for this session.
  }
};

export const oneOf = <T extends string>(allowed: readonly T[]) => (value: unknown): T | null =>
  typeof value === 'string' && (allowed as readonly string[]).includes(value) ? (value as T) : null;

// Keeps the known keys, taking booleans from storage and defaults for the rest.
export const booleanFlags = <K extends string>(defaults: Record<K, boolean>) => (value: unknown): Record<K, boolean> | null => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const stored = value as Record<string, unknown>;
  const result = { ...defaults };
  for (const key of Object.keys(defaults) as K[]) {
    if (typeof stored[key] === 'boolean') result[key] = stored[key] as boolean;
  }
  return result;
};
