import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

// The panels are covered by their own tests; here they only report the symbol.
vi.mock('../components/Sidebar', () => ({
  default: ({ currentSymbol, onSymbolChange }: { currentSymbol: string; onSymbolChange: (symbol: string) => void }) => (
    <div>
      <span data-testid="sidebar-symbol">{currentSymbol}</span>
      <button onClick={() => onSymbolChange('AAPL')}>pick AAPL</button>
      <input aria-label="chat" />
    </div>
  ),
}));
vi.mock('../components/ChartPanel', () => ({ default: () => <div /> }));
vi.mock('../components/BottomPanel', () => ({ default: () => <div /> }));
vi.mock('../components/StrategyBuilder', () => ({ default: () => <div /> }));

describe('App', () => {
  let store: Map<string, string>;

  beforeEach(() => {
    store = new Map();
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => { store.set(key, String(value)); },
        removeItem: (key: string) => { store.delete(key); },
        clear: () => store.clear(),
      },
    });
  });

  it('reopens on the last symbol you viewed', () => {
    const { unmount } = render(<App />);
    expect(screen.getByTestId('sidebar-symbol')).toHaveTextContent('BTC/USDT');
    fireEvent.click(screen.getByText('pick AAPL'));
    unmount();

    render(<App />);
    expect(screen.getByTestId('sidebar-symbol')).toHaveTextContent('AAPL');
  });

  it('ignores a corrupt saved symbol', () => {
    store.set('astral.chart.symbol', JSON.stringify('<img src=x>'));
    render(<App />);
    expect(screen.getByTestId('sidebar-symbol')).toHaveTextContent('BTC/USDT');
  });

  it('shows the shortcut list with "?" and closes it with Escape', async () => {
    render(<App />);
    expect(screen.queryByRole('dialog', { name: 'Keyboard shortcuts' })).toBeNull();

    await act(async () => { fireEvent.keyDown(screen.getByLabelText('chat'), { key: '?' }); });
    expect(screen.queryByRole('dialog', { name: 'Keyboard shortcuts' })).toBeNull();

    await act(async () => { fireEvent.keyDown(window, { key: '?' }); });
    expect(screen.getByRole('dialog', { name: 'Keyboard shortcuts' })).toHaveTextContent('Search the watchlist');

    await act(async () => { fireEvent.keyDown(window, { key: 'Escape' }); });
    expect(screen.queryByRole('dialog', { name: 'Keyboard shortcuts' })).toBeNull();
  });
});
