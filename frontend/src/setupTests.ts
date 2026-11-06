import '@testing-library/jest-dom';
import { beforeEach } from 'vitest';

// Every test gets its own empty localStorage. jsdom's real one (on Node 20,
// as in CI) persists across tests, so a timeframe or watchlist saved by one
// test leaked into the next; newer Node versions provide none at all.
beforeEach(() => {
  const store = new Map<string, string>();
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, String(value)); },
      removeItem: (key: string) => { store.delete(key); },
      clear: () => store.clear(),
      key: (index: number) => Array.from(store.keys())[index] ?? null,
      get length() { return store.size; },
    },
  });
});
