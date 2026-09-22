import React from 'react';
import { render, screen } from '@testing-library/react';
import StrategyBuilder from '../StrategyBuilder';
import { describe, it, expect, vi } from 'vitest';

// Basic stub for react-flow since jsdom handles SVG/canvas differently
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: any) => <div data-testid="react-flow-mock">{children}</div>,
  Controls: () => <div />,
  Background: () => <div />,
  MiniMap: () => <div />,
  useNodesState: () => [[], vi.fn()],
  useEdgesState: () => [[], vi.fn()],
  addEdge: vi.fn(),
}));

describe('StrategyBuilder Component', () => {
  it('renders standard canvas tools without crashing', () => {
    // We expect StrategyBuilder to have a prop or local state 
    // Just rendering it to ensure no catastrophic syntax errors
    const { container } = render(<StrategyBuilder />);
    
    // Strategy Builder uses xyflow, expect either our mock to mount or a specific UI component
    expect(container).toBeTruthy();
  });
});
