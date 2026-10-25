import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import Sidebar from '../Sidebar';

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
