import { useState } from 'react';
import axios from 'axios';
import { BACKEND_URL } from '../lib/api';

type CheckStatus = 'ok' | 'warning' | 'error' | 'skipped';
type ConnectionCheck = { id: string; name: string; status: CheckStatus; message: string; elapsed_ms?: number };
type ConnectionReport = { checked_at: string; checks: ConnectionCheck[] };

const STATUS_STYLE: Record<CheckStatus, { icon: string; className: string; label: string }> = {
  ok: { icon: '✅', className: 'text-green-400', label: 'Working' },
  warning: { icon: '⚠️', className: 'text-amber-400', label: 'Needs attention' },
  error: { icon: '❌', className: 'text-red-400', label: 'Not working' },
  skipped: { icon: '➖', className: 'text-gray-500', label: 'Not checked' },
};

// Settings -> "Test connections": runs the backend's read-only checks of the
// market data sources, the AI provider and any broker with saved keys.
export default function ConnectionStatus() {
  const [report, setReport] = useState<ConnectionReport | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  const runChecks = async () => {
    setRunning(true);
    setError('');
    try {
      const res = await axios.post<ConnectionReport>(`${BACKEND_URL}/api/diagnostics/connections`, {}, { timeout: 90_000 });
      setReport(res.data);
    } catch (err) {
      setReport(null);
      setError(axios.isAxiosError(err) && !err.response
        ? 'The Astral backend could not be reached. Make sure it is running.'
        : 'The connection test could not run.');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="rounded-lg border border-[#2a2a35] bg-[#0a0a0c] p-3" data-testid="connection-status">
      <div className="flex items-center justify-between gap-2">
        <span className="text-gray-300 font-medium">Connection status</span>
        <button
          type="button"
          onClick={() => void runChecks()}
          disabled={running}
          className="text-[11px] px-3 py-1.5 rounded-md bg-[#a55eea] text-white hover:bg-[#b87ef7] disabled:opacity-50"
        >
          {running ? 'Testing…' : 'Test connections'}
        </button>
      </div>
      <p className="text-[10px] text-gray-500 mt-1.5 leading-relaxed">
        Checks live prices, stock data, your AI provider and every broker with saved keys. Brokers get a read-only
        balance lookup in your chosen environment (demo/testnet when switched on); no orders are ever sent. Can take up to half a minute.
      </p>
      {error && <p role="alert" className="text-[11px] text-red-400 mt-2">{error}</p>}
      {report && (
        <ul className="mt-2 space-y-1.5">
          {report.checks.map((check) => {
            const style = STATUS_STYLE[check.status] ?? STATUS_STYLE.error;
            return (
              <li key={check.id} data-testid={`check-${check.id}`} data-status={check.status} className="text-[11px] leading-snug">
                <span aria-label={style.label} title={style.label}>{style.icon}</span>{' '}
                <span className={`font-semibold ${style.className}`}>{check.name}</span>
                <span className="text-gray-400"> — {check.message}</span>
              </li>
            );
          })}
          <li className="text-[10px] text-gray-600 pt-1">Checked {new Date(report.checked_at).toLocaleTimeString()}</li>
        </ul>
      )}
    </div>
  );
}
