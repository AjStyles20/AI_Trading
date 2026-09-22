import React from 'react';
import { render, screen } from '@testing-library/react';
import BottomPanel from '../BottomPanel';
import { describe, it, expect, vi } from 'vitest';

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
    const { container } = render(<BottomPanel {...dummyProps} />);
    
    // Should display the Code tab
    const codeTabList = screen.getAllByText(/Code/i);
    expect(codeTabList.length).toBeGreaterThan(0);
    
    // Check if Terminal tab exists
    const terminalTabList = screen.getAllByText(/Terminal/i);
    expect(terminalTabList.length).toBeGreaterThan(0);
  });
});
