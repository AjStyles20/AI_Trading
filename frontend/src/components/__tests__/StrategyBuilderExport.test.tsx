import type { ReactNode } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import StrategyBuilder, { type StrategyBuilderGraph } from '../StrategyBuilder';

vi.mock('axios', () => ({ default: { post: vi.fn() } }));

// Keeps the graph passed in, so the export sees a real, valid flow.
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Controls: () => <div />,
  Background: () => <div />,
  MiniMap: () => <div />,
  useNodesState: (initial: unknown) => [initial, vi.fn(), vi.fn()],
  useEdgesState: (initial: unknown) => [initial, vi.fn(), vi.fn()],
  addEdge: vi.fn(),
}));

const node = (id: string, label: string, category: string, payload?: Record<string, number | string>) => ({
  id, data: { label, category, payload }, position: { x: 0, y: 0 },
});

const graph = {
  nodes: [
    node('1', 'Start Strategy', 'entry'),
    node('2', 'RSI (indicator)', 'indicator', { indicator: 'RSI', period: 21 }),
    node('3', 'RSI < 28 (condition)', 'condition', { operator: '<', value: 28 }),
    node('4', 'BUY (action)', 'action', { side: 'buy' }),
  ],
  edges: [
    { id: 'a', source: '1', target: '2' },
    { id: 'b', source: '2', target: '3' },
    { id: 'c', source: '3', target: '4' },
  ],
} as unknown as StrategyBuilderGraph;

describe('StrategyBuilder AI export', () => {
  afterEach(() => { vi.restoreAllMocks(); });

  it('sends each node\'s settings, not just the shape of the graph', async () => {
    vi.spyOn(window, 'alert').mockImplementation(() => {});
    vi.mocked(axios.post).mockResolvedValue({ data: { status: 'success', code: 'def strategy(df):\n    return df' } });
    const setStrategyCode = vi.fn();
    render(<StrategyBuilder initialGraph={graph} setStrategyCode={setStrategyCode} />);

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'AI Export' })); });

    const body = vi.mocked(axios.post).mock.calls[0][1] as { nodes: { id: string; settings?: unknown }[] };
    expect(body.nodes.find((item) => item.id === '2')?.settings).toEqual({ indicator: 'RSI', period: 21 });
    expect(body.nodes.find((item) => item.id === '3')?.settings).toEqual({ operator: '<', value: 28 });
    expect(setStrategyCode).toHaveBeenCalled();
  });
});
