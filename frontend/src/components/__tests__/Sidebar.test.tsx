import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import Sidebar from '../Sidebar';
import { fromStoredMessages, toMarkdownTranscript, transcriptFilename } from '../../lib/chatTranscript';
import { markdownToHtml, messageToHtml, transcriptToHtml, wordDocument } from '../../lib/chatDocument';
import {
  attachmentCaptionText,
  checkImageFile,
  checkVideoFile,
  formatClipTime,
  frameTimes,
  prepareImageAttachment,
  prepareVideoFrames,
  scaledSize,
} from '../../lib/imageAttachments';

// Image decoding and resizing need a real browser; tests stand in for it.
vi.mock('../../lib/imageAttachments', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../lib/imageAttachments')>()),
  prepareImageAttachment: vi.fn(),
  prepareVideoFrames: vi.fn(),
}));

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

    fireEvent.click(screen.getByText('.md'));

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
      { query: 'first', images: [], conversation_id: 'main_session' }, expect.anything());

    fireEvent.click(screen.getByText('New'));
    expect(screen.queryByText('first')).toBeNull();
    const newId = window.localStorage.getItem('astral.chat.conversationId');
    expect(newId).toMatch(/^chat-\d+$/);

    await send('second');
    expect(post).toHaveBeenLastCalledWith(expect.stringContaining('/api/chat'),
      { query: 'second', images: [], conversation_id: newId }, expect.anything());
  });
});

describe('chat document (Word) helpers', () => {
  it('renders Markdown tables with visible borders for word processors', () => {
    const html = markdownToHtml('| Rule | Value |\n|---|---|\n| Stop | 2% |');
    expect(html).toContain('<table border="1"');
    expect(html).toContain('<td>2%</td>');
  });

  it('escapes HTML from messages instead of passing it through', () => {
    const html = markdownToHtml('Look <img src="x" onerror="alert(1)"> <script>alert(2)</script>');
    expect(html).not.toContain('<img');
    expect(html).not.toContain('<script');
  });

  it('keeps the user\'s own text literal, with line breaks', () => {
    const html = messageToHtml({ id: '1', role: 'user', text: '## not a heading\nnext line', timestamp: '' });
    expect(html).not.toContain('<h2');
    expect(html).toContain('## not a heading<br/>next line');
  });

  it('wraps a transcript in a Word-compatible document', () => {
    const body = transcriptToHtml([
      { id: '1', role: 'user', text: 'Explain RSI', timestamp: '4:19 PM' },
      { id: '2', role: 'assistant', text: '**RSI** measures momentum.', timestamp: '4:20 PM' },
    ]);
    const doc = wordDocument(body);
    expect(doc).toContain('xmlns:w="urn:schemas-microsoft-com:office:word"');
    expect(doc).toContain('<strong>You</strong> · 4:19 PM');
    expect(doc).toContain('<strong>RSI</strong> measures momentum.');
    expect(doc.indexOf('Explain RSI')).toBeLessThan(doc.indexOf('measures momentum'));
  });
});

describe('Sidebar chat: Word-friendly copy and export', () => {
  const configured = { ...savedSettings, ai_provider: 'groq', credential_presence: { groq: true } };
  const history = [
    { role: 'user', content: 'Show rules', created_at: '2026-10-25 14:19:34' },
    { role: 'assistant', content: '| Rule | Value |\n|---|---|\n| Stop | 2% |', created_at: '2026-10-25 14:19:46' },
  ];
  let written: Record<string, Blob>[];

  beforeEach(() => {
    get.mockReset();
    get.mockImplementation((url: string) => Promise.resolve(
      String(url).endsWith('/api/chat/history') ? { data: { messages: history } } : { data: configured },
    ));
    Element.prototype.scrollIntoView = vi.fn();
    written = [];
    class FakeClipboardItem {
      items: Record<string, Blob>;
      constructor(items: Record<string, Blob>) { this.items = items; }
    }
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        write: vi.fn(async (items: FakeClipboardItem[]) => { written.push(items[0].items); }),
        writeText: vi.fn(async () => {}),
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const renderChat = async () => {
    render(<Sidebar activeView="chart" onViewChange={vi.fn()} currentSymbol="BTC/USDT" onSymbolChange={vi.fn()} />);
    await act(async () => {});
  };

  it('copies a single reply as formatted HTML plus plain text', async () => {
    await renderChat();
    const copyButtons = screen.getAllByLabelText('Copy message');
    await act(async () => { fireEvent.click(copyButtons[copyButtons.length - 1]); });

    expect(written).toHaveLength(1);
    expect(await written[0]['text/html'].text()).toContain('<table border="1"');
    expect(await written[0]['text/plain'].text()).toContain('| Stop | 2% |');
  });

  it('copies the whole conversation formatted', async () => {
    await renderChat();
    await act(async () => { fireEvent.click(screen.getByText('Copy all')); });

    const html = await written[0]['text/html'].text();
    expect(html).toContain('Show rules');
    expect(html).toContain('<td>2%</td>');
  });

  it('saves the conversation as a Word document', async () => {
    let saved: Blob | undefined;
    URL.createObjectURL = vi.fn((blob: Blob) => { saved = blob; return 'blob:word'; });
    URL.revokeObjectURL = vi.fn();
    let filename = '';
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      filename = this.download;
    });
    await renderChat();

    await act(async () => { fireEvent.click(screen.getByText('Word')); });

    expect(filename).toMatch(/^astral-chat-\d{4}-\d{2}-\d{2}-\d{4}\.doc$/);
    expect(saved!.type).toBe('application/msword;charset=utf-8');
    expect(await saved!.text()).toContain('<td>2%</td>');
  });
});

describe('image attachment rules', () => {
  const file = (name: string, type: string, size = 10) => new File([new Uint8Array(size)], name, { type });

  it('accepts common image types and rejects everything else', () => {
    expect(checkImageFile(file('chart.png', 'image/png'))).toBeNull();
    expect(checkImageFile(file('photo.jpg', 'image/jpeg'))).toBeNull();
    expect(checkImageFile(file('notes.pdf', 'application/pdf'))).toContain('only PNG, JPEG, WebP or GIF');
    expect(checkImageFile(file('vector.svg', 'image/svg+xml'))).toContain('only PNG, JPEG, WebP or GIF');
  });

  it('rejects files above the source size limit', () => {
    const huge = file('huge.png', 'image/png');
    Object.defineProperty(huge, 'size', { value: 26 * 1024 * 1024 });
    expect(checkImageFile(huge)).toContain('larger than 25 MB');
  });

  it('scales the longest side down to the limit and never enlarges', () => {
    expect(scaledSize(4000, 3000)).toEqual({ width: 1600, height: 1200 });
    expect(scaledSize(1000, 3200)).toEqual({ width: 500, height: 1600 });
    expect(scaledSize(800, 600)).toEqual({ width: 800, height: 600 });
  });
});

describe('Sidebar chat: image attachments', () => {
  const configured = { ...savedSettings, ai_provider: 'groq', ai_vision_model: 'vision-x', credential_presence: { groq: true } };
  const png = (name = 'chart.png') => new File([new Uint8Array(8)], name, { type: 'image/png' });

  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockImplementation((url: string) => Promise.resolve(
      String(url).endsWith('/api/chat/history') ? { data: { messages: [] } } : { data: configured },
    ));
    post.mockResolvedValue({ data: { response: 'A rising wedge.', status: 'success' } });
    Element.prototype.scrollIntoView = vi.fn();
    vi.mocked(prepareImageAttachment).mockReset();
    vi.mocked(prepareImageAttachment).mockImplementation(async (file: File) => ({
      id: file.name, name: file.name, dataUrl: `data:image/png;base64,${btoa(file.name)}`,
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderChat = async () => {
    render(<Sidebar activeView="chart" onViewChange={vi.fn()} currentSymbol="BTC/USDT" onSymbolChange={vi.fn()} />);
    await act(async () => {});
  };
  const attach = async (...files: File[]) => {
    await act(async () => { fireEvent.change(screen.getByTestId('image-file-input'), { target: { files } }); });
  };
  const chatInput = () => screen.getByPlaceholderText('Ask AI to analyze...');

  it('previews attached images and sends them with the message', async () => {
    await renderChat();
    await attach(png('chart.png'));
    expect(screen.getByAltText('chart.png')).toBeInTheDocument();

    fireEvent.change(chatInput(), { target: { value: 'What pattern is this?' } });
    await act(async () => { fireEvent.keyDown(chatInput(), { key: 'Enter' }); });

    const [, payload] = post.mock.calls.find(([url]) => String(url).endsWith('/api/chat'))!;
    expect(payload).toMatchObject({ query: 'What pattern is this?', images: [`data:image/png;base64,${btoa('chart.png')}`] });
    expect(screen.queryByTestId('attachment-previews')).toBeNull();
    expect(screen.getByAltText('Attached image 1')).toBeInTheDocument();
    expect(screen.getByText('A rising wedge.')).toBeInTheDocument();
  });

  it('can send an image with no text', async () => {
    await renderChat();
    await attach(png());
    await act(async () => { fireEvent.click(screen.getByLabelText('Attach images').parentElement!.querySelectorAll('button')[1]); });

    const [, payload] = post.mock.calls.find(([url]) => String(url).endsWith('/api/chat'))!;
    expect(payload).toMatchObject({ query: '', images: [expect.stringMatching(/^data:image\/png;base64,/)] });
  });

  it('removes an attachment before sending', async () => {
    await renderChat();
    await attach(png('a.png'), png('b.png'));
    fireEvent.click(screen.getByLabelText('Remove a.png'));

    expect(screen.queryByAltText('a.png')).toBeNull();
    expect(screen.getByAltText('b.png')).toBeInTheDocument();
  });

  it('limits a message to four images and says why', async () => {
    await renderChat();
    await attach(png('1.png'), png('2.png'), png('3.png'), png('4.png'), png('5.png'));

    expect(screen.getAllByAltText(/^\d\.png$/)).toHaveLength(4);
    expect(screen.getByRole('alert')).toHaveTextContent('Only 4 images can be attached per message.');
  });

  it('reports files that cannot be attached', async () => {
    vi.mocked(prepareImageAttachment).mockRejectedValueOnce(new Error('notes.pdf: only PNG, JPEG, WebP or GIF images can be attached.'));
    await renderChat();
    await attach(new File(['x'], 'notes.pdf', { type: 'application/pdf' }));

    expect(screen.getByRole('alert')).toHaveTextContent('notes.pdf: only PNG, JPEG, WebP or GIF');
    expect(screen.queryByTestId('attachment-previews')).toBeNull();
  });

  it('attaches a pasted screenshot', async () => {
    await renderChat();
    await act(async () => { fireEvent.paste(chatInput(), { clipboardData: { files: [png('screenshot.png')] } }); });

    expect(screen.getByAltText('screenshot.png')).toBeInTheDocument();
  });

  it('saves the vision model chosen in Settings', async () => {
    await renderChat();
    fireEvent.click(screen.getByTitle('Settings'));
    fireEvent.change(screen.getByPlaceholderText('An image-capable Groq model'), { target: { value: 'vision-y' } });
    await act(async () => { fireEvent.click(screen.getByText('Save Configuration')); });

    const [, payload] = post.mock.calls.find(([url]) => String(url).endsWith('/api/settings'))!;
    expect(payload).toMatchObject({ ai_vision_model: 'vision-y' });
  });
});

describe('video frame rules', () => {
  it('accepts MP4, WebM and MOV videos only', () => {
    expect(checkVideoFile(new File(['x'], 'clip.mp4', { type: 'video/mp4' }))).toBeNull();
    expect(checkVideoFile(new File(['x'], 'clip.mov', { type: 'video/quicktime' }))).toBeNull();
    expect(checkVideoFile(new File(['x'], 'clip.avi', { type: 'video/x-msvideo' }))).toContain('only MP4, WebM or MOV');
  });

  it('spreads frames evenly through the clip', () => {
    expect(frameTimes(40, 4)).toEqual([5, 15, 25, 35]);
    expect(frameTimes(10, 2)).toEqual([2.5, 7.5]);
    expect(frameTimes(Number.NaN, 4)).toEqual([0]);
  });

  it('formats clip times and captions frames for the AI', () => {
    expect(formatClipTime(65.7)).toBe('1:05');
    const text = attachmentCaptionText([
      { id: '1', name: 'chart.png', dataUrl: 'a' },
      { id: '2', name: 'clip.mp4 @ 0:05', dataUrl: 'b', caption: 'Frame from video "clip.mp4" at 0:05' },
    ]);
    expect(text).toContain('Image 2: Frame from video "clip.mp4" at 0:05');
    expect(text).toContain('sound was not included');
    expect(text).not.toContain('Image 1');
    expect(attachmentCaptionText([{ id: '1', name: 'chart.png', dataUrl: 'a' }])).toBe('');
  });
});

describe('Sidebar chat: video attachments', () => {
  const configured = { ...savedSettings, ai_provider: 'groq', ai_vision_model: 'vision-x', credential_presence: { groq: true } };
  const frames = (name: string, count: number) => Array.from({ length: count }, (_, i) => ({
    id: `${name}-${i}`, name: `${name} @ 0:0${i}`, dataUrl: `data:image/jpeg;base64,${btoa(`${name}${i}`)}`,
    caption: `Frame from video "${name}" at 0:0${i}`,
  }));

  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockImplementation((url: string) => Promise.resolve(
      String(url).endsWith('/api/chat/history') ? { data: { messages: [] } } : { data: configured },
    ));
    post.mockResolvedValue({ data: { response: 'Price broke out.', status: 'success' } });
    Element.prototype.scrollIntoView = vi.fn();
    vi.mocked(prepareImageAttachment).mockReset();
    vi.mocked(prepareImageAttachment).mockImplementation(async (file: File) => ({
      id: file.name, name: file.name, dataUrl: `data:image/png;base64,${btoa(file.name)}`,
    }));
    vi.mocked(prepareVideoFrames).mockReset();
    vi.mocked(prepareVideoFrames).mockImplementation(async (file: File, count = 4) => frames(file.name, count));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderChat = async () => {
    render(<Sidebar activeView="chart" onViewChange={vi.fn()} currentSymbol="BTC/USDT" onSymbolChange={vi.fn()} />);
    await act(async () => {});
  };
  const attach = async (...files: File[]) => {
    await act(async () => { fireEvent.change(screen.getByTestId('image-file-input'), { target: { files } }); });
  };
  const video = (name = 'clip.mp4') => new File([new Uint8Array(8)], name, { type: 'video/mp4' });
  const chatInput = () => screen.getByPlaceholderText('Ask AI to analyze...');

  it('turns a video into frames and tells the AI what they are', async () => {
    await renderChat();
    await attach(video());
    expect(prepareVideoFrames).toHaveBeenCalledWith(expect.any(File), 4);
    expect(screen.getAllByAltText(/^clip\.mp4 @/)).toHaveLength(4);

    fireEvent.change(chatInput(), { target: { value: 'What happens in this clip?' } });
    await act(async () => { fireEvent.keyDown(chatInput(), { key: 'Enter' }); });

    const [, payload] = post.mock.calls.find(([url]) => String(url).endsWith('/api/chat'))!;
    const { query, images } = payload as { query: string; images: string[] };
    expect(images).toHaveLength(4);
    expect(query.startsWith('What happens in this clip?')).toBe(true);
    expect(query).toContain('Image 1: Frame from video "clip.mp4" at 0:00');
    expect(query).toContain('sound was not included');
    // The chat shows what you typed; the captions are for the AI.
    expect(screen.getByText('What happens in this clip?')).toBeInTheDocument();
  });

  it('gives a video only the slots that are left', async () => {
    await renderChat();
    await attach(new File(['x'], 'a.png', { type: 'image/png' }), new File(['x'], 'b.png', { type: 'image/png' }));
    await attach(video());

    expect(prepareVideoFrames).toHaveBeenCalledWith(expect.any(File), 2);
    expect(screen.getByTestId('attachment-previews').querySelectorAll('img')).toHaveLength(4);
  });

  it('reports a video that cannot be read', async () => {
    vi.mocked(prepareVideoFrames).mockRejectedValueOnce(new Error('The video could not be read in this app.'));
    await renderChat();
    await attach(video());

    expect(screen.getByRole('alert')).toHaveTextContent('The video could not be read in this app.');
  });
});

describe('Sidebar startup and expanded chat', () => {
  const configured = { ...savedSettings, ai_provider: 'groq', credential_presence: { groq: true } };

  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('keeps retrying settings until a slow-starting backend answers, then loads the chat', async () => {
    vi.useFakeTimers();
    let settingsCalls = 0;
    get.mockImplementation((url: string) => {
      if (String(url).endsWith('/api/chat/history')) {
        return Promise.resolve({ data: { messages: [{ role: 'user', content: 'Saved question', created_at: '2026-10-25 10:00:00' }] } });
      }
      settingsCalls += 1;
      return settingsCalls < 3 ? Promise.reject(new Error('backend starting')) : Promise.resolve({ data: configured });
    });
    render(<Sidebar activeView="chart" onViewChange={vi.fn()} currentSymbol="BTC/USDT" onSymbolChange={vi.fn()} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByPlaceholderText(/Configure an AI provider/)).toBeInTheDocument();
    expect(get).not.toHaveBeenCalledWith(expect.stringContaining('/api/chat/history'), expect.anything());

    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });

    expect(settingsCalls).toBe(3);
    expect(screen.getByPlaceholderText('Ask AI to analyze...')).toBeInTheDocument();
    expect(screen.getByText('Saved question')).toBeInTheDocument();
  });

  it('renders the expanded chat at the top of the page, above everything else', async () => {
    get.mockImplementation((url: string) => Promise.resolve(
      String(url).endsWith('/api/chat/history') ? { data: { messages: [] } } : { data: configured },
    ));
    const { container } = render(<Sidebar activeView="chart" onViewChange={vi.fn()} currentSymbol="BTC/USDT" onSymbolChange={vi.fn()} />);
    await act(async () => {});

    fireEvent.click(screen.getByLabelText('Expand chat'));
    const dialog = document.querySelector('[role=dialog]')!;

    expect(container.contains(dialog)).toBe(false);
    expect(dialog.parentElement!.parentElement).toBe(document.body);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(document.querySelector('[role=dialog]')).toBeNull();
    expect(container.contains(screen.getByPlaceholderText('Ask AI to analyze...'))).toBe(true);
  });
});
