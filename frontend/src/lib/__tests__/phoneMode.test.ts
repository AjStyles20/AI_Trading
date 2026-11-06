import { describe, expect, it, vi } from 'vitest';

const reply = (body: unknown, ok = true, type = 'application/json') =>
  vi.fn(async () => ({ ok, headers: new Headers({ 'content-type': type }), json: async () => body }) as unknown as Response);

describe('detectPhoneMode', () => {
  it('is never on in development, without even asking', async () => {
    const { detectPhoneMode } = await import('../phoneMode');
    const fetchImpl = reply({ read_only: true });
    expect(await detectPhoneMode(fetchImpl)).toBe(false);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  describe('in the built web app', () => {
    it('turns on only for the gateway\'s exact read-only reply', async () => {
      vi.resetModules();
      vi.doMock('../api', () => ({ BACKEND_URL: '' }));
      const { detectPhoneMode } = await import('../phoneMode');

      expect(await detectPhoneMode(reply({ phone: true, read_only: true, device: 'Pixel' }))).toBe(true);
      expect(await detectPhoneMode(reply({ read_only: 'true' }))).toBe(false);
      expect(await detectPhoneMode(reply({ read_only: true }, false))).toBe(false);
      // The desktop app answers unknown paths with its HTML page.
      expect(await detectPhoneMode(reply('<html></html>', true, 'text/html'))).toBe(false);
      expect(await detectPhoneMode(vi.fn(async () => { throw new Error('offline'); }))).toBe(false);
      vi.doUnmock('../api');
    });
  });
});
