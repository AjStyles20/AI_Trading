// The desktop app serves /api from its own origin; Vite development calls the local backend.
export const BACKEND_URL = import.meta.env.DEV ? 'http://127.0.0.1:8000' : '';
