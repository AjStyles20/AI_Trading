import { act, fireEvent, render, screen } from '@testing-library/react';
import axios from 'axios';
import BottomPanel from '../BottomPanel';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
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
