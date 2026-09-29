const path = require('node:path');
const { pathToFileURL } = require('node:url');

const APP_ORIGIN = 'astral://app';
const BACKEND_ORIGIN = 'http://127.0.0.1:8000';

function createProtocolHandler({ net, distDir, desktopToken }) {
  return async (request) => {
    const url = new URL(request.url);
    if (url.protocol !== 'astral:' || url.host !== 'app' || url.username || url.password) {
      return new Response('Not found', { status: 404 });
    }

    if (url.pathname.startsWith('/api/')) {
      const headers = new Headers(request.headers);
      // The backend receives a local request, not a request to the custom scheme.
      for (const name of ['host', 'origin', 'content-length']) headers.delete(name);
      if (desktopToken) headers.set('x-astral-desktop-token', desktopToken);
      try {
        return await net.fetch(`${BACKEND_ORIGIN}${url.pathname}${url.search}`, {
          method: request.method,
          headers,
          body: request.body || undefined,
        });
      } catch {
        return new Response('Local backend unavailable. Start python backend/main.py and retry.', {
          status: 503,
          headers: { 'content-type': 'text/plain' },
        });
      }
    }

    let filePath;
    try {
      if (/%2f|%5c/i.test(url.pathname)) return new Response('Bad path', { status: 400 });
      const name = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname);
      if (name.includes('\\')) return new Response('Bad path', { status: 400 });
      filePath = path.resolve(distDir, `.${name}`);
    } catch {
      return new Response('Bad path', { status: 400 });
    }
    const relative = path.relative(distDir, filePath);
    if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) {
      return new Response('Not found', { status: 404 });
    }
    try {
      return await net.fetch(pathToFileURL(filePath).toString());
    } catch {
      return new Response('Not found', { status: 404 });
    }
  };
}

module.exports = { APP_ORIGIN, createProtocolHandler };
