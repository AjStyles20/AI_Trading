import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import Sidebar from '../Sidebar';
import { fromStoredMessages, toMarkdownTranscript, transcriptFilename } from '../../lib/chatTranscript';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    isAxiosError: (error: unknown) => Boolean((error as { isAxiosError?: boolean })?.isAxiosError),
  },
}));

const get = vi.mocked(axios.get);
const post = vi.mocked(axios.post);

// What GET /api/settings returns: keys live in the OS credential store, so only
// their presence is reported; broker environments are their own fields.
const savedSettings = {
  theme: 'dark',
  ai_provider: 'groq',
  ai_model: '',
  api_keys: {},
  credential_presence: { groq: true, binance_testnet_key: true, alpaca_paper_secret: true },
  binance_environment: 'testnet',
  bitget_environment: 'live',
};

const renderSidebar = async () => {
  render(<Sidebar activeView="chart" onViewChange={vi.fn()} currentSymbol="BTC/USDT" onSymbolChange={vi.fn()} />);
  await act(async () => {});
  fireEvent.click(screen.getByTitle('Settings'));
};

const checkbox = (label: string) => screen.getByText(label).parentElement!.querySelector('input') as HTMLInputElement;

const save = async () => {
  await act(async () => { fireEvent.click(screen.getByText('Save Configuration')); });
};

const savedPayload = () => post.mock.calls.find(([url]) => String(url).endsWith('/api/settings'))![1] as {
  api_keys: Record<string, string>;
  binance_environment: string;
  bitget_environment: string;
};

describe('Sidebar settings', () => {
  let alertSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockResolvedValue({ data: savedSettings });
    post.mockResolvedValue({ data: { status: 'success' } });
    alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    // jsdom does not implement scrolling; the chat scrolls to its newest message.
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the saved broker environments on the switches', async () => {
    await renderSidebar();

    expect(checkbox('Use Binance Testnet').checked).toBe(true);
    expect(checkbox('Use Bitget Demo Trading').checked).toBe(false);
  });

  it('sends broker environments as settings fields, not as credentials', async () => {
    await renderSidebar();
    await save();

    const payload = savedPayload();
    expect(payload.binance_environment).toBe('testnet');
    expect(payload.bitget_environment).toBe('live');
    expect(payload.api_keys).not.toHaveProperty('binance_testnet');
    expect(payload.api_keys).not.toHaveProperty('bitget_demo');
  });

  it('keeps keys that are stored in the credential store when saving', async () => {
    await renderSidebar();
    await save();

    const { api_keys: keys } = savedPayload();
    // Masked = "keep the stored key"; empty = "remove it".
    expect(keys.binance_testnet_key).toBe('********');
    expect(keys.alpaca_paper_secret).toBe('********');
    expect(keys.groq).toBe('********');
    expect(keys.bitget_key).toBe('');
  });

  it('saves a toggled switch', async () => {
    await renderSidebar();
    fireEvent.click(checkbox('Use Bitget Demo Trading'));
    fireEvent.click(checkbox('Use Binance Testnet'));
    await save();

    expect(savedPayload().bitget_environment).toBe('demo');
    expect(savedPayload().binance_environment).toBe('live');
  });

  it("shows the backend's reason when it rejects a save", async () => {
    post.mockRejectedValue({ isAxiosError: true, response: { status: 400, data: { detail: 'OS credential store could not be updated.' } } });
    await renderSidebar();
    await save();

    expect(alertSpy).toHaveBeenCalledWith('Failed to save settings: OS credential store could not be updated.');
  });

  it('only blames the connection when the backend cannot be reached', async () => {
    post.mockRejectedValue({ isAxiosError: true });
    await renderSidebar();
    await save();

    expect(alertSpy).toHaveBeenCalledWith(expect.stringContaining('could not be reached'));
  });
});

describe('chat transcript helpers', () => {
  it('turns stored messages into chat messages with readable times', () => {
    const messages = fromStoredMessages([
      { role: 'user', content: 'hi', created_at: '2026-10-25 14:13:10' },
      { role: 'assistant', content: 'hello', created_at: null },
    ]);
    expect(messages.map((m) => [m.role, m.text])).toEqual([['user', 'hi'], ['assistant', 'hello']]);
    expect(messages[0].timestamp).toBe(new Date('2026-10-25T14:13:10Z').toLocaleString());
    expect(messages[1].timestamp).toBe('');
  });

  it('exports the conversation as Markdown with speakers in order', () => {
    const markdown = toMarkdownTranscript([
      { id: '1', role: 'user', text: 'What is RSI?', timestamp: '4:19 PM' },
      { id: '2', role: 'assistant', text: '## RSI\n\nA momentum gauge.', timestamp: '4:20 PM' },
    ], new Date(2026, 9, 25, 16, 30));
    expect(markdown).toContain('# Astral AI conversation');
    expect(markdown.indexOf('**You** · 4:19 PM')).toBeLessThan(markdown.indexOf('**Astral AI** · 4:20 PM'));
    expect(markdown).toContain('## RSI\n\nA momentum gauge.');
  });

  it('names exported files by date and time', () => {
    expect(transcriptFilename(new Date(2026, 9, 5, 9, 7))).toBe('astral-chat-2026-10-05-0907.md');
  });
});

describe('Sidebar chat', () => {
  const configured = { ...savedSettings, ai_provider: 'groq', credential_presence: { groq: true } };
  let history: { role: string; content: string; created_at: string }[];

  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    history = [];
    get.mockImplementation((url: string) => Promise.resolve(
      String(url).endsWith('/api/chat/history') ? { data: { messages: history } } : { data: configured },
    ));
    post.mockResolvedValue({ data: { response: 'Sure.', status: 'success' } });
    Element.prototype.scrollIntoView = vi.fn();
    // In-memory browser storage (not provided by this test environment).
    const store = new Map<string, string>();
    const storage = {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, String(value)); },
      removeItem: (key: string) => { store.delete(key); },
      clear: () => store.clear(),
    };
    Object.defineProperty(window, 'localStorage', { value: storage, configurable: true });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderChat = async () => {
    render(<Sidebar activeView="chart" onViewChange={vi.fn()} currentSymbol="BTC/USDT" onSymbolChange={vi.fn()} />);
    await act(async () => {});
  };

  const send = async (text: string) => {
    fireEvent.change(screen.getByPlaceholderText('Ask AI to analyze...'), { target: { value: text } });
    await act(async () => { fireEvent.keyDown(screen.getByPlaceholderText('Ask AI to analyze...'), { key: 'Enter' }); });
  };

  it('reloads the saved conversation on start', async () => {
    history = [
      { role: 'user', content: 'Explain RSI', created_at: '2026-10-25 14:19:34' },
      { role: 'assistant', content: 'RSI measures momentum.', created_at: '2026-10-25 14:19:46' },
    ];
    await renderChat();

    expect(get).toHaveBeenCalledWith(expect.stringContaining('/api/chat/history'),
      { params: { conversation_id: 'main_session', limit: 500 } });
    expect(screen.getByText('Explain RSI')).toBeInTheDocument();
    expect(screen.getByText('RSI measures momentum.')).toBeInTheDocument();
  });

  it('renders AI replies as formatted Markdown with copyable code', async () => {
    history = [{
      role: 'assistant',
      content: '## Plan\n\n**Bold** idea\n\n| Rule | Value |\n|---|---|\n| Stop | 2% |\n\n```python\nprint(1)\n```',
      created_at: '2026-10-25 14:00:00',
    }];
    await renderChat();

    expect(screen.getByText('Plan').tagName).toMatch(/^H[1-6]$/);
    expect(screen.getByText('Bold').tagName).toBe('STRONG');
    expect(document.querySelector('table')).not.toBeNull();
    expect(screen.getByText('2%').tagName).toBe('TD');
    const code = screen.getByText('print(1)');
    expect(code.closest('pre')).not.toBeNull();
    expect(screen.getAllByText('Copy').length).toBeGreaterThan(0);
  });

  it('never renders HTML from AI replies', async () => {
    history = [{ role: 'assistant', content: 'Look <img src="x" onerror="alert(1)"> <script>alert(2)</script>', created_at: '2026-10-25 14:00:00' }];
    await renderChat();

    expect(document.querySelector('img')).toBeNull();
    expect(document.querySelector('script')).toBeNull();
  });

  it('shows your own messages as plain text, not Markdown', async () => {
    history = [{ role: 'user', content: '## not a heading', created_at: '2026-10-25 14:00:00' }];
    await renderChat();

    expect(screen.getByText('## not a heading').closest('h1, h2, h3, h4, h5, h6')).toBeNull();
    expect(screen.getByText('## not a heading')).toBeInTheDocument();
  });

  it('expands into a large view and closes with Escape', async () => {
    await renderChat();
    fireEvent.click(screen.getByLabelText('Expand chat'));
    expect(document.querySelector('[role=dialog][aria-label="Astral AI chat"]')).not.toBeNull();
    expect(screen.getByText('The chat is open in the expanded view.')).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(document.querySelector('[role=dialog]')).toBeNull();
  });

  it('exports the whole conversation as a Markdown file', async () => {
    history = [
      { role: 'user', content: 'Explain RSI', created_at: '2026-10-25 14:19:34' },
      { role: 'assistant', content: 'RSI measures momentum.', created_at: '2026-10-25 14:19:46' },
    ];
    let exported: Blob | undefined;
    URL.createObjectURL = vi.fn((blob: Blob) => { exported = blob; return 'blob:chat'; });
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await renderChat();

    fireEvent.click(screen.getByText('Export'));

    expect(click).toHaveBeenCalled();
    const text = await exported!.text();
    expect(text).toContain('**You**');
    expect(text).toContain('Explain RSI');
    expect(text).toContain('RSI measures momentum.');
  });

  it('sends messages in the current conversation and starts a new one on request', async () => {
    await renderChat();
    await send('first');
    expect(post).toHaveBeenLastCalledWith(expect.stringContaining('/api/chat'),
      { query: 'first', conversation_id: 'main_session' }, expect.anything());

    fireEvent.click(screen.getByText('New'));
    expect(screen.queryByText('first')).toBeNull();
    const newId = window.localStorage.getItem('astral.chat.conversationId');
    expect(newId).toMatch(/^chat-\d+$/);

    await send('second');
    expect(post).toHaveBeenLastCalledWith(expect.stringContaining('/api/chat'),
      { query: 'second', conversation_id: newId }, expect.anything());
  });
});
