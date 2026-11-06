import { useEffect, useState } from 'react';
import axios from 'axios';

import { BACKEND_URL } from '../lib/api';
import { readPreference, storePreference } from '../lib/preferences';
import { copyText } from '../lib/chatTranscript';
import { isTailscaleAddress } from '../lib/phoneAccess';

type Device = { id: number; name: string; created_at: string; last_seen_at: string | null; revoked_at: string | null };

const ADDRESS_KEY = 'astral.phone.tailscaleAddress';
const GATEWAY_PORT = 8765;

const errorDetail = (err: unknown, fallback: string): string =>
  axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string' ? err.response.data.detail : fallback;

// Pair phones with the read-only phone gateway and revoke them.
export default function PhoneAccessSection() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [address, setAddress] = useState(() => readPreference(ADDRESS_KEY, (v) => (typeof v === 'string' ? v : null), ''));
  const [name, setName] = useState('');
  const [link, setLink] = useState('');
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    axios.get(`${BACKEND_URL}/api/phone/devices`)
      .then((res) => { if (!cancelled) setDevices(Array.isArray(res.data?.items) ? res.data.items : []); })
      .catch((err: unknown) => { if (!cancelled) setError(`Could not list phones: ${errorDetail(err, 'check the backend connection.')}`); });
    return () => { cancelled = true; };
  }, []);

  const pair = async () => {
    setError('');
    setLink('');
    if (!isTailscaleAddress(address)) {
      setError("Enter this computer's Tailscale address (100.x.y.z), shown in the Tailscale app.");
      return;
    }
    if (!name.trim()) {
      setError('Give the phone a name, like "My phone".');
      return;
    }
    try {
      storePreference(ADDRESS_KEY, address.trim());
      const res = await axios.post(`${BACKEND_URL}/api/phone/devices`, { name: name.trim() });
      const { token, ...device } = res.data as Device & { token: string };
      // The token goes in the URL fragment, which the browser never sends to a server.
      setLink(`http://${address.trim()}:${GATEWAY_PORT}/pair#${token}`);
      setDevices((current) => [device, ...current]);
      setName('');
    } catch (err) {
      setError(`Could not pair: ${errorDetail(err, 'check the backend connection.')}`);
    }
  };

  const revoke = async (id: number) => {
    setError('');
    try {
      await axios.delete(`${BACKEND_URL}/api/phone/devices/${id}`);
      setDevices((current) => current.map((d) => (d.id === id ? { ...d, revoked_at: 'now' } : d)));
    } catch (err) {
      setError(`Could not revoke: ${errorDetail(err, 'check the backend connection.')}`);
    }
  };

  const active = devices.filter((d) => !d.revoked_at);

  return (
    <div className="bg-[#1c1c24] p-4 rounded-xl border border-[#2a2a35] space-y-2 text-[10px]">
      <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">Phone access (read-only)</span>
      <p className="text-gray-500 leading-relaxed">
        A paired phone can view charts, positions, the journal and alerts, and arm the kill switch. It cannot trade,
        disarm or change settings. It needs Tailscale on this computer and the phone, and the phone gateway running
        (see the user guide).
      </p>
      <div className="flex flex-wrap gap-2">
        <input
          aria-label="This computer's Tailscale address"
          placeholder="100.x.y.z"
          value={address}
          onChange={(event) => setAddress(event.target.value)}
          className="w-32 bg-[#0a0a0c] border border-[#2a2a35] rounded px-2 py-1 text-white font-mono"
        />
        <input
          aria-label="Phone name"
          placeholder="Phone name"
          maxLength={40}
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="flex-1 min-w-[8rem] bg-[#0a0a0c] border border-[#2a2a35] rounded px-2 py-1 text-white"
        />
        <button type="button" onClick={() => void pair()} className="px-3 py-1 rounded border border-[#a55eea]/60 text-[#a55eea] hover:bg-[#a55eea]/10">
          Pair a phone
        </button>
      </div>
      {link && (
        <div className="rounded border border-amber-500/40 bg-amber-500/5 p-2 space-y-1">
          <p className="text-amber-300">Open this link on the phone. It is shown only once; anyone with it can view your account.</p>
          <div className="flex gap-2 items-center">
            <code data-testid="pairing-link" className="flex-1 break-all text-gray-200">{link}</code>
            <button
              type="button"
              onClick={() => void copyText(link).then((ok) => setCopied(ok))}
              className="shrink-0 px-2 py-0.5 rounded border border-[#2a2a35] text-gray-300"
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="text-red-400">{error}</p>}
      {active.length === 0 && !error && <p className="text-gray-600">No phones paired.</p>}
      <ul className="space-y-1">
        {active.map((device) => (
          <li key={device.id} data-testid="phone-device" className="flex justify-between gap-2 text-gray-400">
            <span>{device.name} · {device.last_seen_at ? `last seen ${device.last_seen_at} UTC` : 'not used yet'}</span>
            <button type="button" onClick={() => void revoke(device.id)} aria-label={`Revoke ${device.name}`} className="text-red-300 hover:underline">
              Revoke
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
