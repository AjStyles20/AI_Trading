import { act, fireEvent, render, screen } from '@testing-library/react';
import axios from 'axios';
import BottomPanel from '../BottomPanel';
import AccountOverview from '../AccountOverview';
import { accountTotal, balanceUsdValue, moneyKind, type AccountSummary } from '../../lib/accountSummary';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
    isAxiosError: (err: unknown) => Boolean((err as { isAxiosError?: boolean })?.isAxiosError),
  }
}));

describe('BottomPanel Component', () => {
  const dummyProps = {
    symbol: 'AAPL',
    assetType: 'stock' as const,
    strategyCode: 'print()',
    setStrategyCode: vi.fn(),
    backtestResults: null,
    setBacktestResults: vi.fn(),
    builderGraph: { nodes: [], edges: [] },
    onLoadStrategy: vi.fn(),
  };

  it('renders without crashing and displays default tabs', () => {
    render(<BottomPanel {...dummyProps} />);
    
    // Should display the Code tab
    const codeTabList = screen.getAllByText(/Code/i);
    expect(codeTabList.length).toBeGreaterThan(0);
    
    // Check if Terminal tab exists
    const terminalTabList = screen.getAllByText(/Terminal/i);
    expect(terminalTabList.length).toBeGreaterThan(0);
  });

  it.each([
    ['Run Backtest', '/api/backtest/run', 'Backtest failed'],
    ['Optimize', '/api/strategy/optimize', 'Optimization failed'],
  ])('shows the backend reason when %s fails', async (button, endpoint, prefix) => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    vi.mocked(axios.get).mockImplementation((url: string) => {
      const path = String(url);
      if (path.includes('/api/trading/history')) return Promise.resolve({ data: [] });
      if (path.includes('/api/trading/account/')) {
        return Promise.resolve({ data: { broker_id: 'paper', configured: true, can_trade: true, balances: [], warnings: [] } });
      }
      return Promise.resolve({ data: { items: [], logs: [] } });
    });
    vi.mocked(axios.post).mockImplementation((url: string) =>
      String(url).endsWith(endpoint)
        ? Promise.reject({ isAxiosError: true, response: { data: { detail: 'No market data returned for AAPL.' } } })
        : Promise.resolve({ data: {} }),
    );
    render(<BottomPanel {...dummyProps} />);

    await act(async () => {
      // The action button comes before the tab of the same name.
      fireEvent.click(screen.getAllByRole('button', { name: button })[0]);
    });

    expect(await screen.findByText(`${prefix}: No market data returned for AAPL.`)).toBeTruthy();
    expect(alertSpy).not.toHaveBeenCalled();
    alertSpy.mockRestore();
    vi.mocked(axios.post).mockImplementation(() => Promise.resolve({ data: {} }));
  });

  it('shows why saving a strategy failed, in the dialog and then in the workspace list', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    vi.mocked(axios.get).mockImplementation((url: string) => {
      const path = String(url);
      if (path.includes('/api/trading/history')) return Promise.resolve({ data: [] });
      if (path.includes('/api/trading/account/')) {
        return Promise.resolve({ data: { broker_id: 'paper', configured: true, can_trade: true, balances: [], warnings: [] } });
      }
      return Promise.resolve({ data: { items: [], logs: [] } });
    });
    vi.mocked(axios.post).mockImplementation((url: string) =>
      String(url).endsWith('/api/strategies')
        ? Promise.reject({ isAxiosError: true, response: { data: { detail: 'Strategy name already exists.' } } })
        : Promise.resolve({ data: {} }),
    );
    render(<BottomPanel {...dummyProps} />);

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save Workspace' })); });

    const message = 'Could not save the strategy: Strategy name already exists.';
    expect(screen.getByRole('alert')).toHaveTextContent(message);

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.getByRole('alert')).toHaveTextContent(message);
    fireEvent.click(screen.getByLabelText('Dismiss error'));
    expect(screen.queryByText(message)).toBeNull();
    expect(alertSpy).not.toHaveBeenCalled();
    alertSpy.mockRestore();
    vi.mocked(axios.post).mockImplementation(() => Promise.resolve({ data: {} }));
  });

  it('lists settings changes in the Terminal Logs tab, with credentials by name only', async () => {
    vi.mocked(axios.get).mockImplementation((url: string) => {
      const path = String(url);
      if (path.includes('/api/trading/history')) return Promise.resolve({ data: [] });
      if (path.includes('/api/trading/account/')) {
        return Promise.resolve({ data: { broker_id: 'paper', configured: true, can_trade: true, balances: [], warnings: [] } });
      }
      if (path.endsWith('/api/audit')) {
        return Promise.resolve({ data: { items: [{
          id: 1, created_at: '2026-10-30 10:00:00', category: 'settings', action: 'updated',
          details: {
            changes: { autonomy_kill_switch: { from: true, to: false } },
            credentials: { binance_testnet_key: 'set' },
          },
        }] } });
      }
      return Promise.resolve({ data: { items: [], logs: [] } });
    });
    render(<BottomPanel {...dummyProps} />);

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Terminal Logs' })); });

    expect(await screen.findByTestId('audit-event')).toHaveTextContent(
      'autonomy_kill_switch: true → false; binance_testnet_key set',
    );
  });

  it('optimizes the default ranges within the backend limit of 1,000 combinations', async () => {
    const post = vi.mocked(axios.post);
    post.mockClear();
    render(<BottomPanel {...dummyProps} />);

    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name: 'Optimize' })[0]);
    });

    const call = post.mock.calls.find(([url]) => String(url).endsWith('/api/strategy/optimize'));
    const ranges = (call?.[1] as { custom_ranges: Record<string, number[]> }).custom_ranges;
    const combinations = Object.values(ranges).reduce((total, values) => total * values.length, 1);
    expect(combinations).toBeGreaterThan(1);
    expect(combinations).toBeLessThanOrEqual(1000);
  });
});

describe('BottomPanel background refresh', () => {
  const props = {
    symbol: 'BTC/USDT',
    assetType: 'crypto' as const,
    strategyCode: 'print()',
    setStrategyCode: vi.fn(),
    backtestResults: null,
    setBacktestResults: vi.fn(),
    builderGraph: { nodes: [], edges: [] },
    onLoadStrategy: vi.fn(),
  };
  let loopActive = false;
  const get = vi.mocked(axios.get);
  const statusCalls = () => get.mock.calls.filter(([url]) => String(url).endsWith('/api/trading/status')).length;
  const setVisibility = (state: 'visible' | 'hidden') =>
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });

  beforeEach(() => {
    vi.useFakeTimers();
    loopActive = false;
    setVisibility('visible');
    get.mockReset();
    get.mockImplementation((url: string) => {
      const path = String(url);
      if (path.endsWith('/api/trading/status')) {
        return Promise.resolve({ data: { is_active: loopActive, logs: [], config: { broker_id: 'paper', execution_mode: 'paper' } } });
      }
      if (path.endsWith('/api/trading/brokers')) {
        return Promise.resolve({ data: { items: [
          { broker_id: 'paper', display_name: 'Paper Broker', configured: true },
          { broker_id: 'bitget', display_name: 'Bitget', configured: true },
        ] } });
      }
      if (path.includes('/api/trading/history')) return Promise.resolve({ data: [] });
      if (path.includes('/api/trading/account/')) {
        return Promise.resolve({ data: { broker_id: 'paper', configured: true, can_trade: true, balances: [], warnings: [] } });
      }
      return Promise.resolve({ data: { items: [] } });
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
  const brokerSelect = () => screen.getByText('Broker').querySelector('select') as HTMLSelectElement;
  const modeSelect = () => screen.getByText('Execution Mode').querySelector('select') as HTMLSelectElement;

  it('keeps the broker and mode you chose while the trading loop is stopped', async () => {
    render(<BottomPanel {...props} />);
    await tick(0);
    fireEvent.change(brokerSelect(), { target: { value: 'bitget' } });
    fireEvent.change(modeSelect(), { target: { value: 'live' } });

    await tick(15_000);

    expect(brokerSelect().value).toBe('bitget');
    expect(modeSelect().value).toBe('live');
  });

  it('follows the running loop\'s broker and mode while it runs', async () => {
    loopActive = true;
    render(<BottomPanel {...props} />);
    await tick(0);
    fireEvent.change(brokerSelect(), { target: { value: 'bitget' } });

    await tick(5_000);

    expect(brokerSelect().value).toBe('paper');
  });

  it('pauses while the tab is hidden and catches up when it is shown', async () => {
    render(<BottomPanel {...props} />);
    await tick(0);
    const afterLoad = statusCalls();

    setVisibility('hidden');
    await tick(30_000);
    expect(statusCalls()).toBe(afterLoad);

    setVisibility('visible');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(statusCalls()).toBe(afterLoad + 1);
  });

  it('never starts a refresh while the previous one is still running', async () => {
    let releaseStatus!: () => void;
    const slowStatus = new Promise((resolve) => { releaseStatus = () => resolve({ data: { is_active: false, logs: [] } }); });
    render(<BottomPanel {...props} />);
    await tick(0);
    const base = get.getMockImplementation()!;
    get.mockImplementation((url: string) => (String(url).endsWith('/api/trading/status') ? slowStatus as never : base(url)));
    const before = statusCalls();

    await tick(20_000);
    expect(statusCalls()).toBe(before + 1);

    await act(async () => { releaseStatus(); await vi.advanceTimersByTimeAsync(5_000); });
    expect(statusCalls()).toBe(before + 2);
  });
});

describe('Account panel', () => {
  const unifiedDemo: AccountSummary = {
    broker_id: 'bitget', display_name: 'Bitget', execution_mode: 'live', environment: 'demo', account_type: 'unified',
    configured: true, can_trade: false, total_equity_usd: 4762170.08, warnings: ['Bitget demo mode is enabled.'],
    balances: [
      { asset: 'BTC', free: 59.37, locked: 0, usd_value: 4700000 },
      { asset: 'USDT', free: 49000, locked: 1000, usd_value: 50000 },
      { asset: 'preSPCX', free: 1000, locked: 0, usd_value: 12170.08 },
    ],
  };
  const renderPanel = (props: Partial<Parameters<typeof AccountOverview>[0]> = {}) => render(
    <AccountOverview summary={unifiedDemo} executionMode="live" updatedAt={new Date(2026, 9, 26, 6, 30)}
      refreshing={false} error="" onRefresh={vi.fn()} {...props} />,
  );

  it('labels the kind of money unmistakably', () => {
    expect(moneyKind(null, 'paper').label).toBe('PAPER');
    expect(moneyKind(unifiedDemo, 'live')).toMatchObject({ label: 'DEMO', detail: 'Practice money' });
    expect(moneyKind({ ...unifiedDemo, environment: 'testnet' }, 'live').label).toBe('TESTNET');
    expect(moneyKind({ ...unifiedDemo, environment: 'live' }, 'live')).toMatchObject({ label: 'LIVE', detail: 'Real money' });
  });

  it('totals the account from the broker figure, or from priced coins', () => {
    expect(accountTotal(unifiedDemo)).toEqual({ total: 4762170.08, complete: true });
    const classic: AccountSummary = { ...unifiedDemo, total_equity_usd: null, balances: [
      { asset: 'USDT', free: 100, locked: 5 }, { asset: 'BTC', free: 1, locked: 0 },
    ] };
    expect(balanceUsdValue(classic.balances[0])).toBe(105);
    expect(balanceUsdValue(classic.balances[1])).toBeNull();
    expect(accountTotal(classic)).toEqual({ total: 105, complete: false });
    expect(accountTotal({ ...classic, balances: [{ asset: 'BTC', free: 1, locked: 0 }] })).toEqual({ total: null, complete: false });
  });

  it('shows the total, every coin and that the account is read-only', () => {
    renderPanel();

    expect(screen.getByTestId('money-kind')).toHaveTextContent('DEMO · Practice money');
    expect(screen.getByText(/Unified account/)).toBeInTheDocument();
    expect(screen.getByTestId('account-total')).toHaveTextContent('$4,762,170.08');
    expect(screen.getByTestId('account-trading')).toHaveTextContent('Read-only');
    const rows = screen.getByTestId('account-balances').querySelectorAll('tbody tr');
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent('BTC59.37059.37$4,700,000.00');
    expect(rows[1]).toHaveTextContent('USDT49,0001,00050,000$50,000.00');
    expect(screen.getByText(/Updated/)).toBeInTheDocument();
  });

  it('marks real-money accounts in red and explains a missing total', () => {
    renderPanel({ summary: { ...unifiedDemo, environment: 'live', account_type: 'classic', can_trade: true, total_equity_usd: null,
      balances: [{ asset: 'ETH', free: 2, locked: 0 }] } });

    expect(screen.getByTestId('money-kind')).toHaveTextContent('LIVE · Real money');
    expect(screen.getByTestId('money-kind').className).toContain('text-red-300');
    expect(screen.getByTestId('account-total')).toHaveTextContent('—');
    expect(screen.getByText('This broker does not report account value.')).toBeInTheDocument();
  });

  it('refreshes on request and shows errors instead of stale numbers', () => {
    const onRefresh = vi.fn();
    renderPanel({ summary: null, onRefresh, error: 'Could not load the account: Bitget network error: timed out' });

    expect(screen.getByRole('alert')).toHaveTextContent('Bitget network error');
    expect(screen.queryByTestId('account-balances')).toBeNull();
    fireEvent.click(screen.getByText('Refresh'));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
