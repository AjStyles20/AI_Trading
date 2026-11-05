import { useEffect, useState } from 'react';
import axios from 'axios';

import { BACKEND_URL } from '../lib/api';

type Memory = { id: string; text: string; created_at: string | null };

const errorDetail = (err: unknown, fallback: string): string =>
  axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string' ? err.response.data.detail : fallback;

const PREVIEW_CHARS = 160;

// The past exchanges the AI recalls into new conversations. Users can see and
// remove them; forgetting cannot be undone.
export default function MemorySection() {
  const [items, setItems] = useState<Memory[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    axios.get(`${BACKEND_URL}/api/ai/memory`, { params: { limit: 100 } })
      .then((res) => {
        if (cancelled) return;
        setItems(Array.isArray(res.data?.items) ? res.data.items : []);
        setTotal(typeof res.data?.total === 'number' ? res.data.total : null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(`Could not load AI memory: ${errorDetail(err, 'check the backend connection.')}`);
      });
    return () => { cancelled = true; };
  }, []);

  const forget = async (id: string) => {
    setError('');
    try {
      await axios.delete(`${BACKEND_URL}/api/ai/memory/${encodeURIComponent(id)}`);
      setItems((current) => current.filter((item) => item.id !== id));
      setTotal((current) => (current === null ? null : Math.max(0, current - 1)));
    } catch (err) {
      setError(`Could not forget that memory: ${errorDetail(err, 'check the backend connection.')}`);
    }
  };

  const forgetAll = async () => {
    if (!window.confirm('Forget everything the AI remembers from past conversations? This cannot be undone.')) return;
    setError('');
    try {
      await axios.post(`${BACKEND_URL}/api/ai/memory/forget-all`, { confirm: true });
      setItems([]);
      setTotal(0);
    } catch (err) {
      setError(`Could not forget AI memory: ${errorDetail(err, 'check the backend connection.')}`);
    }
  };

  return (
    <div className="bg-[#1c1c24] p-4 rounded-xl border border-[#2a2a35] space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">
          AI memory{total !== null && <span className="ml-1 font-normal text-gray-500 normal-case">({total})</span>}
        </span>
        {items.length > 0 && (
          <button
            type="button"
            onClick={() => void forgetAll()}
            className="px-3 py-1 rounded border border-red-500/50 text-[11px] text-red-300 hover:bg-red-500/10"
          >
            Forget everything
          </button>
        )}
      </div>
      <p className="text-[10px] text-gray-500 leading-relaxed">
        Past exchanges the AI can recall in new conversations. They are stored on this computer, separately from
        backups. Forgetting cannot be undone. Your chat history is kept either way.
      </p>
      {error && <p role="alert" className="text-[10px] text-red-400">{error}</p>}
      {!error && total === 0 && <p className="text-[10px] text-gray-600">The AI remembers nothing yet.</p>}
      <ul className="max-h-60 overflow-y-auto space-y-2">
        {items.map((item) => (
          <li key={item.id} data-testid="memory-item" className="flex items-start gap-2 text-[10px]">
            <div className="flex-1 min-w-0">
              <div className="text-gray-600">{item.created_at ? `${item.created_at} UTC` : 'Undated'}</div>
              <div className="text-gray-300 break-words">
                {item.text.length > PREVIEW_CHARS ? `${item.text.slice(0, PREVIEW_CHARS)}…` : item.text}
              </div>
            </div>
            <button
              type="button"
              onClick={() => void forget(item.id)}
              aria-label={`Forget memory from ${item.created_at ?? 'an undated conversation'}`}
              className="shrink-0 px-2 py-0.5 rounded border border-[#2a2a35] text-gray-400 hover:text-red-300 hover:border-red-500/50"
            >
              Forget
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
