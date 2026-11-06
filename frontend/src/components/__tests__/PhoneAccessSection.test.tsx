import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import PhoneAccessSection from '../PhoneAccessSection';
import { isTailscaleAddress } from '../../lib/phoneAccess';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    put: vi.fn(),
    isAxiosError: (error: unknown) => Boolean((error as { isAxiosError?: boolean })?.isAxiosError),
  },
}));

const get = vi.mocked(axios.get);
const post = vi.mocked(axios.post);
const del = vi.mocked(axios.delete);
const put = vi.mocked(axios.put);

describe('Tailscale address check', () => {
  it('accepts only 100.64.0.0 to 100.127.255.255', () => {
    for (const ok of ['100.64.0.1', '100.101.102.103', '100.127.255.255']) expect(isTailscaleAddress(ok)).toBe(true);
    for (const bad of ['', '192.168.1.5', '100.63.0.1', '100.128.0.1', '100.64.0', '100.64.0.256', '0.0.0.0', 'my-pc'])
      expect(isTailscaleAddress(bad)).toBe(false);
  });
});

describe('PhoneAccessSection', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    del.mockReset();
    put.mockReset();
    get.mockImplementation(async (url: string) => (String(url).endsWith('/api/phone/gateway') ? { data: { host: null } } : { data: { items: [
      { id: 2, name: 'Old phone', created_at: 'x', last_seen_at: null, revoked_at: '2026-11-01' },
      { id: 1, name: 'Pixel', created_at: 'x', last_seen_at: '2026-11-05 10:00:00', revoked_at: null },
    ] } }));
  });

  const renderSection = async () => {
    render(<PhoneAccessSection />);
    await act(async () => {});
  };

  it('lists only phones that still have access', async () => {
    await renderSection();
    const devices = screen.getAllByTestId('phone-device');
    expect(devices).toHaveLength(1);
    expect(devices[0]).toHaveTextContent('Pixel · last seen 2026-11-05 10:00:00 UTC');
  });

  it('refuses a non-Tailscale address before pairing', async () => {
    await renderSection();
    fireEvent.change(screen.getByLabelText("This computer's Tailscale address"), { target: { value: '192.168.1.20' } });
    fireEvent.change(screen.getByLabelText('Phone name'), { target: { value: 'Pixel 2' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Pair a phone' })); });

    expect(post).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Tailscale address (100.x.y.z)');
  });

  it('pairs and shows the link once, with the token only in the fragment', async () => {
    post.mockResolvedValue({ data: { id: 3, name: 'Pixel 2', created_at: 'x', last_seen_at: null, revoked_at: null, token: 'SECRET-TOKEN' } });
    await renderSection();
    fireEvent.change(screen.getByLabelText("This computer's Tailscale address"), { target: { value: '100.101.102.103' } });
    fireEvent.change(screen.getByLabelText('Phone name'), { target: { value: 'Pixel 2' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Pair a phone' })); });

    expect(post).toHaveBeenCalledWith(expect.stringContaining('/api/phone/devices'), { name: 'Pixel 2' });
    expect(screen.getByTestId('pairing-link')).toHaveTextContent('http://100.101.102.103:8765/pair#SECRET-TOKEN');
    expect(screen.getByText(/shown only once/)).toBeInTheDocument();
    expect(screen.getAllByTestId('phone-device')).toHaveLength(2);
    expect(window.localStorage.getItem('astral.phone.tailscaleAddress')).toBe('"100.101.102.103"');
  });

  it('revokes a phone', async () => {
    del.mockResolvedValue({ data: { status: 'revoked' } });
    await renderSection();

    await act(async () => { fireEvent.click(screen.getByLabelText('Revoke Pixel')); });

    expect(del).toHaveBeenCalledWith(expect.stringContaining('/api/phone/devices/1'));
    expect(screen.queryAllByTestId('phone-device')).toHaveLength(0);
  });
  it('turns phone access on for a Tailscale address and off again', async () => {
    put.mockImplementation(async (_url: string, body: unknown) => ({ data: body }));
    await renderSection();
    expect(screen.getByTestId('gateway-status')).toHaveTextContent('Off');

    fireEvent.change(screen.getByLabelText("This computer's Tailscale address"), { target: { value: '192.168.1.5' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Turn on' })); });
    expect(put).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("This computer's Tailscale address"), { target: { value: '100.101.102.103' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Turn on' })); });
    expect(put).toHaveBeenCalledWith(expect.stringContaining('/api/phone/gateway'), { host: '100.101.102.103' });
    expect(screen.getByTestId('gateway-status')).toHaveTextContent('On at 100.101.102.103');

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Turn off' })); });
    expect(put).toHaveBeenLastCalledWith(expect.stringContaining('/api/phone/gateway'), { host: null });
    expect(screen.getByTestId('gateway-status')).toHaveTextContent('Off');
  });

});
