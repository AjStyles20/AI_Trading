const test = require('node:test');
const assert = require('node:assert/strict');
const { createProtocolHandler } = require('./protocol.cjs');

test('serves only bundled files under the desktop origin', async () => {
  const fetched = [];
  const handler = createProtocolHandler({
    distDir: '/app/dist',
    net: { fetch: async (url) => { fetched.push(url); return new Response('ok'); } },
  });

  assert.equal((await handler({ url: 'astral://app/' })).status, 200);
  assert.equal((await handler({ url: 'astral://app/assets/main.js' })).status, 200);
  assert.deepEqual(fetched, ['file:///app/dist/index.html', 'file:///app/dist/assets/main.js']);
  assert.equal((await handler({ url: 'astral://other/assets/main.js' })).status, 404);
  assert.equal((await handler({ url: 'astral://app/%2fetc/passwd' })).status, 400);
  assert.equal(fetched.length, 2);
});

test('forwards API method and body to loopback and reports an unavailable backend', async () => {
  let forwarded;
  const handler = createProtocolHandler({
    distDir: '/app/dist',
    net: { fetch: async (url, options) => {
      // Real fetch validates upload body semantics; a mock accepting any stream
      // missed the packaged POST failure.
      const actualRequest = new Request(url, options);
      assert.equal(await actualRequest.text(), 'test-body');
      forwarded = { url, options };
      return new Response('{"ok":true}', { headers: { 'content-type': 'application/json' } });
    } },
  });
  const result = await handler(new Request('astral://app/api/trading/status?scope=paper', {
    method: 'POST',
    headers: { origin: 'astral://app', 'content-type': 'application/json', 'sec-fetch-site': 'cross-site' },
    body: 'test-body',
  }));
  assert.equal(result.status, 200);
  assert.equal(forwarded.url, 'http://127.0.0.1:8000/api/trading/status?scope=paper');
  assert.equal(forwarded.options.method, 'POST');
  assert.equal(new TextDecoder().decode(forwarded.options.body), 'test-body');
  assert.equal(forwarded.options.headers.get('origin'), null);
  assert.equal(forwarded.options.headers.get('sec-fetch-site'), null);

  const unavailable = createProtocolHandler({
    distDir: '/app/dist',
    net: { fetch: async () => { throw new Error('ECONNREFUSED'); } },
  });
  assert.equal((await unavailable({ url: 'astral://app/api/settings', method: 'GET', headers: {} })).status, 503);
});

test('the packaged desktop injects its token and ignores renderer-supplied tokens', async () => {
  let received;
  const handler = createProtocolHandler({
    distDir: '/app/dist',
    desktopToken: 'private-token',
    net: { fetch: async (_url, options) => { received = options.headers; return new Response('ok'); } },
  });
  await handler({
    url: 'astral://app/api/settings', method: 'GET',
    headers: { 'x-astral-desktop-token': 'forged-token' },
  });
  assert.equal(received.get('x-astral-desktop-token'), 'private-token');
});
