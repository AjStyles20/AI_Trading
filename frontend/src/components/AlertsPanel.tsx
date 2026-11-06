import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

import { BACKEND_URL } from '../lib/api';
import {
  ALERT_CHECK_MS,
  describeAlert,
  isCrossed,
  notify,
  parseAlertPrice,
  type AlertDirection,
  type PriceAlert,
} from '../lib/alerts';
import { assetTypeFor, parseQuote, quotePath } from '../lib/watchlist';

const errorDetail = (err: unknown, fallback: string): string =>
  axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string' ? err.response.data.detail : fallback;

export default function AlertsPanel({ currentSymbol, backendOnline }: { currentSymbol: string; backendOnline: boolean }) {
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [direction, setDirection] = useState<AlertDirection>('above');
  const [priceInput, setPriceInput] = useState('');
  const [error, setError] = useState('');
  const [justTriggered, setJustTriggered] = useState<number[]>([]);
  const [permission, setPermission] = useState(() => (typeof Notification === 'undefined' ? 'unsupported' : Notification.permission));
  const loadAlerts = useCallback(async (): Promise<PriceAlert[] | null> => {
    try {
      const res = await axios.get(`${BACKEND_URL}/api/alerts`);
      const items: PriceAlert[] = Array.isArray(res.data?.items) ? res.data.items : [];
      setAlerts(items);
      return items;
    } catch {
      // Offline: keep showing what we have; the next check retries.
      return null;
    }
  }, []);

  // Check active alerts against fresh quotes, one symbol at a time.
  useEffect(() => {
    if (!backendOnline) return;
    let cancelled = false;
    const check = async () => {
      const items = await loadAlerts();
      if (!items || cancelled) return;
      const active = items.filter((alert) => alert.triggered_at === null);
      const symbols = Array.from(new Set(active.map((alert) => alert.symbol)));
      for (const symbol of symbols) {
        if (cancelled) return;
        let price: number | null = null;
        try {
          price = parseQuote((await axios.get(`${BACKEND_URL}${quotePath(symbol)}`)).data)?.price ?? null;
        } catch {
          price = null;
        }
        if (price === null) continue;
        for (const alert of active.filter((item) => item.symbol === symbol && isCrossed(item, price))) {
          if (cancelled) return;
          try {
            // The backend re-checks the crossing before recording it.
            const res = await axios.post(`${BACKEND_URL}/api/alerts/${alert.id}/trigger`, { price });
            const triggered = res.data as PriceAlert;
            setAlerts((current) => current.map((item) => (item.id === triggered.id ? triggered : item)));
            setJustTriggered((current) => [...current, triggered.id]);
            notify('Astral price alert', `${describeAlert(alert)} — now ${price.toLocaleString()}`);
          } catch {
            // Rejected or offline: it stays active and is checked again.
          }
        }
      }
    };
    void check();
    // Keeps checking while the window is hidden: that is when a notification matters.
    const timer = window.setInterval(() => { void check(); }, ALERT_CHECK_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [backendOnline, loadAlerts]);

  const addAlert = async () => {
    setError('');
    const price = parseAlertPrice(priceInput);
    if (price === null) {
      setError('Enter a price above zero.');
      return;
    }
    try {
      const res = await axios.post(`${BACKEND_URL}/api/alerts`, {
        symbol: currentSymbol,
        asset_type: assetTypeFor(currentSymbol),
        direction,
        price,
      });
      setAlerts((current) => [...current, res.data as PriceAlert]);
      setPriceInput('');
    } catch (err) {
      setError(`Could not add the alert: ${errorDetail(err, 'check the backend connection.')}`);
    }
  };

  const removeAlert = async (id: number) => {
    try {
      await axios.delete(`${BACKEND_URL}/api/alerts/${id}`);
      setAlerts((current) => current.filter((alert) => alert.id !== id));
    } catch (err) {
      setError(`Could not delete the alert: ${errorDetail(err, 'check the backend connection.')}`);
    }
  };

  const enableNotifications = async () => {
    if (typeof Notification === 'undefined') return;
    setPermission(await Notification.requestPermission());
  };

  const active = alerts.filter((alert) => alert.triggered_at === null);
  const triggered = alerts.filter((alert) => alert.triggered_at !== null);

  return (
    <div className="px-3 pb-3 space-y-2 text-[10px]">
      <div className="flex items-center gap-1">
        <select
          aria-label="Alert direction"
          value={direction}
          onChange={(event) => setDirection(event.target.value as AlertDirection)}
          className="bg-[#0a0a0c] border border-[#2a2a35] rounded px-1 py-1 text-white"
        >
          <option value="above">{currentSymbol} ≥</option>
          <option value="below">{currentSymbol} ≤</option>
        </select>
        <input
          aria-label="Alert price"
          inputMode="decimal"
          placeholder="Price"
          value={priceInput}
          onChange={(event) => { setPriceInput(event.target.value); setError(''); }}
          onKeyDown={(event) => { if (event.key === 'Enter') void addAlert(); }}
          className="min-w-0 flex-1 bg-[#0a0a0c] border border-[#2a2a35] rounded px-2 py-1 text-white"
        />
        <button type="button" onClick={() => void addAlert()} className="px-2 py-1 rounded border border-[#a55eea]/60 text-[#a55eea] hover:bg-[#a55eea]/10">
          Add
        </button>
      </div>
      {error && <p role="alert" className="text-red-400">{error}</p>}

      {active.map((alert) => (
        <div key={alert.id} className="flex items-center justify-between text-gray-400">
          <span>{describeAlert(alert)}</span>
          <button type="button" aria-label={`Delete alert ${describeAlert(alert)}`} onClick={() => void removeAlert(alert.id)} className="text-gray-600 hover:text-red-400">×</button>
        </div>
      ))}
      {triggered.map((alert) => (
        <div
          key={alert.id}
          data-testid={`triggered-${alert.id}`}
          className={`flex items-center justify-between ${justTriggered.includes(alert.id) ? 'text-amber-300' : 'text-gray-600'}`}
        >
          <span>✓ {describeAlert(alert)} — hit at {alert.triggered_price?.toLocaleString()}</span>
          <button type="button" aria-label={`Delete alert ${describeAlert(alert)}`} onClick={() => void removeAlert(alert.id)} className="hover:text-red-400">×</button>
        </div>
      ))}

      <p className="text-gray-600">
        Alerts are checked about every 30 seconds while Astral is open.
        {permission === 'default' && (
          <> <button type="button" onClick={() => void enableNotifications()} className="text-[#a55eea] hover:underline">Turn on desktop notifications</button></>
        )}
        {permission === 'denied' && ' Desktop notifications are blocked; triggered alerts still show here.'}
      </p>
    </div>
  );
}
