import { useState } from 'react';

const DISARM_CONFIRMATION = 'DISARM';

type SessionConfig = {
  symbol?: string;
  interval?: string;
  broker_id?: string;
  execution_mode?: string;
};

// The one autonomous session the trading loop can run, and the emergency controls.
// `killSwitchArmed` is undefined until the first read and null when it could not
// be read: neither ever shows as safe. Disarming needs DISARM typed in full, and the
// backend allows it for paper trading only.
export default function TradingSessionPanel({
  isRunning,
  config,
  killSwitchArmed,
  isArming,
  isDisarming,
  error,
  onArm,
  onDisarm,
  onStop,
  readOnly = false,
}: {
  isRunning: boolean;
  config: SessionConfig | null;
  killSwitchArmed: boolean | null | undefined;
  isArming: boolean;
  isDisarming: boolean;
  error: string;
  onArm: () => void;
  onDisarm: (confirmation: string) => void;
  onStop: () => void;
  // On a phone only arming is possible; disarm and stop are hidden.
  readOnly?: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState('');
  const isLive = config?.execution_mode === 'live';
  const canOfferDisarm = !readOnly && killSwitchArmed === true && !(isRunning && isLive);
  const killSwitchLabel =
    killSwitchArmed === undefined ? 'CHECKING' : killSwitchArmed === null ? 'UNKNOWN' : killSwitchArmed ? 'ARMED' : 'DISARMED';
  const killSwitchClass =
    killSwitchArmed === null || killSwitchArmed === undefined
      ? 'text-amber-300 border-amber-500/40 bg-amber-500/10'
      : killSwitchArmed
        ? 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10'
        : 'text-red-300 border-red-500/40 bg-red-500/10';

  const explanation =
    killSwitchArmed === undefined
      ? 'Checking the kill switch state...'
      : killSwitchArmed === null
      ? 'Kill switch state could not be read. Check the backend connection.'
      : !killSwitchArmed
        ? 'Autonomous orders are allowed within your risk limits. Arm the kill switch to block new ones.'
        : isRunning
          ? 'The loop is only observing and reconciling. It creates no new orders while armed.'
          : 'New autonomous orders are blocked, and a session cannot start while armed.';

  return (
    <section aria-label="Trading session" className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3 mt-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] uppercase tracking-widest text-gray-500">Trading session</span>
        <span data-testid="session-state" className={`px-2 py-0.5 rounded border text-[10px] font-bold ${isRunning ? 'text-green-300 border-green-500/40 bg-green-500/10' : 'text-gray-400 border-[#2a2a35]'}`}>
          {isRunning ? 'RUNNING' : 'IDLE'}
        </span>
        <span data-testid="kill-switch-state" className={`px-2 py-0.5 rounded border text-[10px] font-bold ${killSwitchClass}`}>
          KILL SWITCH {killSwitchLabel}
        </span>
        {isRunning && config && (
          <span data-testid="session-details" className="text-gray-300">
            {config.symbol} · {config.interval} · {config.broker_id} ·{' '}
            <span className={isLive ? 'text-red-400 font-bold' : 'text-gray-300'}>{isLive ? 'LIVE' : 'paper'}</span>
          </span>
        )}
        <div className="ml-auto flex gap-2">
          {killSwitchArmed !== true && (
            <button
              type="button"
              onClick={onArm}
              disabled={isArming}
              className="px-3 py-1 rounded bg-red-600 text-white font-semibold hover:bg-red-500 disabled:opacity-50"
            >
              {isArming ? 'Arming...' : 'Arm kill switch'}
            </button>
          )}
          {canOfferDisarm && !confirming && (
            <button
              type="button"
              onClick={() => { setConfirming(true); setTyped(''); }}
              className="px-3 py-1 rounded border border-[#2a2a35] text-gray-400 hover:border-gray-500 hover:text-gray-200"
            >
              Disarm for paper trading
            </button>
          )}
          {isRunning && !readOnly && (
            <button
              type="button"
              onClick={onStop}
              className="px-3 py-1 rounded border border-[#2a2a35] text-gray-200 hover:border-gray-500"
            >
              Stop session
            </button>
          )}
        </div>
      </div>
      <p className="mt-2 text-[10px] text-gray-500">{explanation}</p>
      {canOfferDisarm && confirming && (
        <div className="mt-2 rounded border border-red-500/40 bg-red-500/5 p-2 text-[10px] text-gray-300 space-y-2">
          <p>
            Disarming lets a paper session place simulated orders on its own, within your risk limits. It is refused
            while live trading is enabled, and live trading cannot be enabled until you arm again. Type {DISARM_CONFIRMATION} to confirm.
          </p>
          <div className="flex items-center gap-2">
            <input
              aria-label="Type DISARM to confirm"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              autoComplete="off"
              className="w-28 bg-[#0a0a0c] border border-[#2a2a35] rounded px-2 py-1 text-white font-mono"
            />
            <button
              type="button"
              onClick={() => onDisarm(typed)}
              disabled={typed !== DISARM_CONFIRMATION || isDisarming}
              className="px-3 py-1 rounded border border-red-500/60 text-red-300 hover:bg-red-500/10 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isDisarming ? 'Disarming...' : 'Confirm disarm'}
            </button>
            <button type="button" onClick={() => setConfirming(false)} className="px-2 py-1 text-gray-500 hover:text-gray-300">
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="mt-1 text-[10px] text-red-400">{error}</p>}
    </section>
  );
}
