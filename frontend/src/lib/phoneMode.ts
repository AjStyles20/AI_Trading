import { BACKEND_URL } from './api';

// True only when the built web app is being served by the read-only phone
// gateway to a paired phone. The desktop app and the dev server never are.
export const detectPhoneMode = async (fetchImpl: typeof fetch = fetch): Promise<boolean> => {
  if (BACKEND_URL !== '' || !/^https?:$/.test(window.location.protocol)) return false;
  try {
    const response = await fetchImpl('/phone/session', { credentials: 'same-origin' });
    if (!response.ok || !(response.headers.get('content-type') ?? '').includes('application/json')) return false;
    const body = await response.json();
    return body?.read_only === true;
  } catch {
    return false;
  }
};
