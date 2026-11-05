import { useEffect, useState } from 'react';
import axios from 'axios';

import { BACKEND_URL } from '../lib/api';

type Backup = { name: string; size_bytes: number; created: string };

const errorDetail = (err: unknown, fallback: string): string =>
  axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string' ? err.response.data.detail : fallback;

const formatSize = (bytes: number): string =>
  bytes >= 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

// Backups of settings, strategies, trades, alerts, journal and chat history.
// They stay on this computer; nothing is uploaded.
export default function BackupsSection() {
  const [items, setItems] = useState<Backup[]>([]);
  const [folder, setFolder] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    axios.get(`${BACKEND_URL}/api/backups`)
      .then((res) => {
        if (cancelled) return;
        setItems(Array.isArray(res.data?.items) ? res.data.items : []);
        setFolder(typeof res.data?.folder === 'string' ? res.data.folder : '');
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(`Could not list backups: ${errorDetail(err, 'check the backend connection.')}`);
      });
    return () => { cancelled = true; };
  }, []);

  const backUpNow = async () => {
    if (busy) return;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const res = await axios.post(`${BACKEND_URL}/api/backups`);
      const created = res.data?.backup as Backup;
      setItems((current) => [created, ...current.filter((item) => item.name !== created.name)].slice(0, 10));
      setMessage(`Saved ${created.name}`);
    } catch (err) {
      setError(errorDetail(err, 'Backup failed: check the backend connection.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-[#1c1c24] p-4 rounded-xl border border-[#2a2a35] space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">Backups</span>
        <button
          type="button"
          onClick={() => void backUpNow()}
          disabled={busy}
          className="px-3 py-1 rounded border border-[#a55eea]/60 text-[11px] text-[#a55eea] hover:bg-[#a55eea]/10 disabled:opacity-50"
        >
          {busy ? 'Backing up...' : 'Back up now'}
        </button>
      </div>
      <p className="text-[10px] text-gray-500 leading-relaxed">
        Saves settings, strategies, trades, alerts, the journal and chat history to this computer only; the newest
        10 are kept. API keys are in your system's credential store and are not included.
        {folder && <> Folder: <span className="font-mono break-all text-gray-400">{folder}</span></>}
      </p>
      {message && <p className="text-[10px] text-emerald-400">{message}</p>}
      {error && <p role="alert" className="text-[10px] text-red-400">{error}</p>}
      {items.length === 0 && !error && <p className="text-[10px] text-gray-600">No backups yet.</p>}
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item.name} data-testid="backup-item" className="flex justify-between gap-2 text-[10px] text-gray-400">
            <span>{item.created}</span>
            <span className="text-gray-600">{formatSize(item.size_bytes)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
