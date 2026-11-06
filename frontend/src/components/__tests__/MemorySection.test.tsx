import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import MemorySection from '../MemorySection';

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

const memories = [
  { id: 'a/1', text: 'User asked: gold trend\nAI Responded: ' + 'x'.repeat(300), created_at: '2026-11-05 09:00:00' },
  { id: 'b', text: 'User asked: likes RSI', created_at: null },
];

describe('MemorySection', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    del.mockReset();
    get.mockResolvedValue({ data: { total: 2, items: memories } });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderSection = async () => {
    render(<MemorySection />);
    await act(async () => {});
  };

  it('lists what the AI remembers, shortened, with dates', async () => {
    await renderSection();

    const items = screen.getAllByTestId('memory-item');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('2026-11-05 09:00:00 UTC');
    expect(items[0].textContent).toContain('…');
    expect(items[1]).toHaveTextContent('Undated');
    expect(screen.getByText('(2)')).toBeInTheDocument();
  });

  it('forgets one memory, encoding its id in the address', async () => {
    del.mockResolvedValue({ data: { status: 'forgotten' } });
    await renderSection();

    await act(async () => { fireEvent.click(screen.getByLabelText('Forget memory from 2026-11-05 09:00:00')); });

    expect(del).toHaveBeenCalledWith(expect.stringMatching(/\/api\/ai\/memory\/a%2F1$/));
    expect(screen.getAllByTestId('memory-item')).toHaveLength(1);
    expect(screen.getByText('(1)')).toBeInTheDocument();
  });

  it('forgets everything only after confirming', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    post.mockResolvedValue({ data: { forgotten: 2 } });
    await renderSection();

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Forget everything' })); });
    expect(post).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Forget everything' })); });
    expect(post).toHaveBeenCalledWith(expect.stringContaining('/api/ai/memory/forget-all'), { confirm: true });
    expect(screen.queryAllByTestId('memory-item')).toHaveLength(0);
    expect(screen.getByText('The AI remembers nothing yet.')).toBeInTheDocument();
  });

  it('shows why loading failed', async () => {
    get.mockRejectedValue({ isAxiosError: true, response: { data: { detail: 'memory store unavailable' } } });
    await renderSection();

    expect(screen.getByRole('alert')).toHaveTextContent('Could not load AI memory: memory store unavailable');
  });
});
