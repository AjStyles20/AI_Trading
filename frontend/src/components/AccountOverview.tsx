// The selected broker account at a glance: which money it is (paper, demo or
// real), total value, and every coin with its value.

import {
  accountTotal,
  balanceUsdValue,
  formatAmount,
  formatUsd,
  moneyKind,
  type AccountSummary,
} from '../lib/accountSummary';

type Props = {
  summary: AccountSummary | null;
  executionMode: string;
  updatedAt: Date | null;
  refreshing: boolean;
  error: string;
  onRefresh: () => void;
};

export default function AccountOverview({ summary, executionMode, updatedAt, refreshing, error, onRefresh }: Props) {
  const kind = moneyKind(summary, executionMode);
  const total = summary ? accountTotal(summary) : { total: null, complete: false };

  return (
    <section className="border-b border-[#2a2a35] py-3" data-testid="account-overview" aria-label="Account">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] uppercase tracking-widest text-gray-500">Account</span>
        <span data-testid="money-kind" className={`text-[10px] font-bold px-2 py-0.5 rounded border ${kind.className}`} title={kind.detail}>
          {kind.label} · {kind.detail}
        </span>
        {summary && (
          <span className="text-xs text-gray-300">
            {summary.display_name}
            {summary.account_type ? ` · ${summary.account_type === 'unified' ? 'Unified account' : 'Classic account'}` : ''}
          </span>
        )}
        <span className="ml-auto flex items-center gap-2 text-[10px] text-gray-500">
          {updatedAt && <span>Updated {updatedAt.toLocaleTimeString()}</span>}
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="px-2 py-1 rounded border border-[#2a2a35] text-gray-300 hover:text-white hover:border-[#a55eea] disabled:opacity-50"
          >
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </span>
      </div>

      {error && <p role="alert" className="mt-2 text-[11px] text-red-300">{error}</p>}

      {summary && (
        <>
          <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2">
            <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
              <div className="text-[10px] uppercase tracking-widest text-gray-500">Total value</div>
              <div className="text-lg font-bold text-white tabular-nums mt-0.5" data-testid="account-total">
                {total.total !== null ? formatUsd(total.total) : '—'}
              </div>
              {total.total !== null && !total.complete && (
                <div className="text-[10px] text-gray-500">Priced coins only; this broker does not report every coin&apos;s value.</div>
              )}
              {total.total === null && <div className="text-[10px] text-gray-500">This broker does not report account value.</div>}
            </div>
            <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
              <div className="text-[10px] uppercase tracking-widest text-gray-500">Trading</div>
              <div className={`text-sm font-bold mt-1 ${summary.can_trade ? 'text-emerald-300' : 'text-amber-300'}`} data-testid="account-trading">
                {summary.can_trade ? 'Enabled' : 'Read-only'}
              </div>
              {!summary.can_trade && (
                <div className="text-[10px] text-gray-500">
                  {summary.configured ? 'Orders are blocked for this account.' : 'Add this broker’s keys in Settings.'}
                </div>
              )}
            </div>
            <div className="bg-[#16161e] border border-[#2a2a35] rounded-lg p-3">
              <div className="text-[10px] uppercase tracking-widest text-gray-500">Holdings</div>
              <div className="text-sm font-bold text-white mt-1">
                {summary.balances.length} {summary.balances.length === 1 ? 'coin' : 'coins'}
              </div>
            </div>
          </div>

          {summary.balances.length > 0 ? (
            <div className="mt-2 overflow-x-auto rounded-lg border border-[#2a2a35]">
              <table className="min-w-full text-xs" data-testid="account-balances">
                <thead className="bg-[#14141b] text-gray-400">
                  <tr>
                    <th className="text-left font-semibold px-3 py-1.5">Coin</th>
                    <th className="text-right font-semibold px-3 py-1.5">Available</th>
                    <th className="text-right font-semibold px-3 py-1.5">Locked</th>
                    <th className="text-right font-semibold px-3 py-1.5">Total</th>
                    <th className="text-right font-semibold px-3 py-1.5">Value (USD)</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.balances.map((balance) => {
                    const value = balanceUsdValue(balance);
                    return (
                      <tr key={balance.asset} className="border-t border-[#2a2a35] text-white tabular-nums">
                        <td className="px-3 py-1.5 font-semibold">{balance.asset}</td>
                        <td className="px-3 py-1.5 text-right">{formatAmount(balance.free)}</td>
                        <td className="px-3 py-1.5 text-right text-gray-400">{formatAmount(balance.locked)}</td>
                        <td className="px-3 py-1.5 text-right">{formatAmount(balance.free + balance.locked)}</td>
                        <td className="px-3 py-1.5 text-right">{value !== null ? formatUsd(value) : '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mt-2 text-[11px] text-gray-500">No balances in this account.</p>
          )}

          {summary.warnings.length > 0 && (
            <div className="mt-2 text-[10px] text-amber-300">{summary.warnings.join(' | ')}</div>
          )}
        </>
      )}
    </section>
  );
}
