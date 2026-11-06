import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import AlertsPanel from '../AlertsPanel';
import { isCrossed, parseAlertPrice } from '../../lib/alerts';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    isAxiosError: (error: unknown) => Boolean((error as { isAxiosError?: boolean })?.isAxiosError),
  },
}));

const get = vi.mocked(axios.get);
const post = vi.mocked(axios.post);
const del = vi.mocked(axios.delete);

const alert = (overrides = {}) => ({
  id: 1, symbol: 'AAPL', asset_type: 'stock', direction: 'above', price: 200, note: '',
  created_at: '2026-10-30 10:00:00', triggered_at: null, triggered_price: null, ...overrides,
});

describe('alert helpers', () => {
  it('detects crossings in either direction and ignores bad prices', () => {
    expect(isCrossed({ direction: 'above', price: 200 }, 200)).toBe(true);
    expect(isCrossed({ direction: 'above', price: 200 }, 199.99)).toBe(false);
    expect(isCrossed({ direction: 'below', price: 50 }, 49)).toBe(true);
    expect(isCrossed({ direction: 'below', price: 50 }, 51)).toBe(false);
    expect(isCrossed({ direction: 'below', price: 50 }, NaN)).toBe(false);
    expect(isCrossed({ direction: 'below', price: 50 }, 0)).toBe(false);
  });

  it('parses typed prices', () => {
    expect(parseAlertPrice('80,000.5')).toBe(80000.5);
    expect(parseAlertPrice(' 12 ')).toBe(12);
    expect(parseAlertPrice('')).toBeNull();
    expect(parseAlertPrice('0')).toBeNull();
    expect(parseAlertPrice('-3')).toBeNull();
    expect(parseAlertPrice('abc')).toBeNull();
  });
});

describe('AlertsPanel', () => {
  let alerts: ReturnType<typeof alert>[];
  let quotePrice: number;
  const shown: { title: string; body?: string }[] = [];

  beforeEach(() => {
    alerts = [];
    quotePrice = 150;
    shown.length = 0;
    get.mockReset();
    post.mockReset();
    del.mockReset();
    get.mockImplementation((url: string) => {
      const path = String(url);
      if (path.endsWith('/api/alerts')) return Promise.resolve({ data: { items: alerts } });
      if (path.includes('/api/market/quote/')) return Promise.resolve({ data: { price: quotePrice, change_pct: 0 } });
      return Promise.reject(new Error(`unexpected ${path}`));
    });
    class FakeNotification {
      static permission = 'granted';
      static requestPermission = vi.fn(async () => 'granted');
      constructor(title: string, options?: { body?: string }) { shown.push({ title, body: options?.body }); }
    }
    vi.stubGlobal('Notification', FakeNotification);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  const renderPanel = async () => {
    render(<AlertsPanel currentSymbol="AAPL" backendOnline />);
    await act(async () => {});
    await act(async () => {});
  };

  it('adds an alert for the symbol on screen and rejects a bad price inline', async () => {
    post.mockResolvedValue({ data: alert({ id: 7, price: 210 }) });
    await renderPanel();

    fireEvent.change(screen.getByLabelText('Alert price'), { target: { value: 'abc' } });
    await act(async () => { fireEvent.click(screen.getByText('Add')); });
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a price above zero.');
    expect(post).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('Alert price'), { target: { value: '210' } });
    await act(async () => { fireEvent.click(screen.getByText('Add')); });
    expect(post).toHaveBeenCalledWith(expect.stringContaining('/api/alerts'), {
      symbol: 'AAPL', asset_type: 'stock', direction: 'above', price: 210,
    });
    expect(screen.getByText('AAPL rises to 210')).toBeInTheDocument();
  });

  it('records and announces an alert once the price reaches it', async () => {
    alerts = [alert()];
    quotePrice = 201;
    post.mockResolvedValue({ data: alert({ triggered_at: '2026-10-30 10:05:00', triggered_price: 201 }) });
    await renderPanel();

    expect(post).toHaveBeenCalledWith(expect.stringContaining('/api/alerts/1/trigger'), { price: 201 });
    expect(screen.getByTestId('triggered-1')).toHaveTextContent('hit at 201');
    expect(shown).toEqual([{ title: 'Astral price alert', body: 'AAPL rises to 200 — now 201' }]);
  });

  it('leaves an alert active while the price has not reached it', async () => {
    alerts = [alert()];
    quotePrice = 150;
    await renderPanel();

    expect(post).not.toHaveBeenCalled();
    expect(screen.getByText('AAPL rises to 200')).toBeInTheDocument();
    expect(shown).toEqual([]);
  });

  it('keeps an alert active when the backend refuses the trigger', async () => {
    alerts = [alert()];
    quotePrice = 201;
    post.mockRejectedValue({ isAxiosError: true, response: { status: 400, data: { detail: 'no' } } });
    await renderPanel();

    expect(screen.queryByTestId('triggered-1')).toBeNull();
    expect(shown).toEqual([]);
  });

  it('checks again on a timer', async () => {
    vi.useFakeTimers();
    alerts = [alert()];
    render(<AlertsPanel currentSymbol="AAPL" backendOnline />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(post).not.toHaveBeenCalled();

    quotePrice = 205;
    post.mockResolvedValue({ data: alert({ triggered_at: '2026-10-30 10:05:00', triggered_price: 205 }) });
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(post).toHaveBeenCalledWith(expect.stringContaining('/api/alerts/1/trigger'), { price: 205 });
  });

  it('deletes an alert', async () => {
    alerts = [alert()];
    del.mockResolvedValue({ data: { status: 'deleted' } });
    await renderPanel();

    await act(async () => { fireEvent.click(screen.getByLabelText('Delete alert AAPL rises to 200')); });
    expect(del).toHaveBeenCalledWith(expect.stringContaining('/api/alerts/1'));
    expect(screen.queryByText('AAPL rises to 200')).toBeNull();
  });
});
