import { useState } from 'react';
import axios from 'axios';

import { BACKEND_URL } from '../lib/api';
import { copyText } from '../lib/chatTranscript';

const errorDetail = (err: unknown, fallback: string): string =>
  axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string' ? err.response.data.detail : fallback;

// A plain-text report to share when asking for help. It is shown in full before
// copying, and nothing is sent anywhere.
export default function DiagnosticsSection() {
  const [report, setReport] = useState('');
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');

  const create = async () => {
    setBusy(true);
    setError('');
    setCopied(false);
    try {
      const res = await axios.get(`${BACKEND_URL}/api/diagnostics/report`);
      setReport(typeof res.data?.report === 'string' ? res.data.report : '');
    } catch (err) {
      setError(`Could not create the report: ${errorDetail(err, 'check the backend connection.')}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-[#1c1c24] p-4 rounded-xl border border-[#2a2a35] space-y-2 text-[10px]">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">Diagnostics report</span>
        <button
          type="button"
          onClick={() => void create()}
          disabled={busy}
          className="px-3 py-1 rounded border border-[#2a2a35] text-[11px] text-gray-300 hover:text-white disabled:opacity-50"
        >
          {busy ? 'Creating...' : 'Create report'}
        </button>
      </div>
      <p className="text-gray-500 leading-relaxed">
        A summary to paste when asking for help: version, safety settings, record counts and recent activity. Key
        values are never included. Read it before sharing; nothing is sent automatically.
      </p>
      {error && <p role="alert" className="text-red-400">{error}</p>}
      {report && (
        <>
          <textarea
            aria-label="Diagnostics report"
            readOnly
            value={report}
            rows={10}
            className="w-full bg-[#0a0a0c] border border-[#2a2a35] rounded p-2 font-mono text-[10px] text-gray-300"
          />
          <button
            type="button"
            onClick={() => void copyText(report).then(setCopied)}
            className="px-3 py-1 rounded border border-[#a55eea]/60 text-[#a55eea] hover:bg-[#a55eea]/10"
          >
            {copied ? 'Copied' : 'Copy report'}
          </button>
        </>
      )}
    </div>
  );
}
