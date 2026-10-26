// Account summary data and helpers shared by the Account panel.

export type AccountBalance = { asset: string; free: number; locked: number; usd_value?: number | null };

export type AccountSummary = {
  broker_id: string;
  display_name: string;
  execution_mode: string;
  environment?: string;
  account_type?: string;
  configured: boolean;
  can_trade: boolean;
  balances: AccountBalance[];
  total_equity_usd?: number | null;
  warnings: string[];
};

const STABLE_USD = new Set(['USD', 'USDT', 'USDC', 'FDUSD', 'DAI']);

const amountFormat = new Intl.NumberFormat('en-US', { maximumFractionDigits: 8 });
const usdFormat = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });

export const formatAmount = (value: number): string => amountFormat.format(value);
export const formatUsd = (value: number): string => usdFormat.format(value);

// A balance's USD value: reported by the broker, or 1:1 for dollar stablecoins.
export const balanceUsdValue = (balance: AccountBalance): number | null => {
  if (typeof balance.usd_value === 'number' && Number.isFinite(balance.usd_value)) return balance.usd_value;
  return STABLE_USD.has(balance.asset.toUpperCase()) ? balance.free + balance.locked : null;
};

// Total in USD: the broker's own figure when given, else the sum of priced
// balances. `complete` is false when some balances could not be priced.
export const accountTotal = (summary: AccountSummary): { total: number | null; complete: boolean } => {
  if (typeof summary.total_equity_usd === 'number' && Number.isFinite(summary.total_equity_usd)) {
    return { total: summary.total_equity_usd, complete: true };
  }
  const values = summary.balances.map(balanceUsdValue);
  const priced = values.filter((value): value is number => value !== null);
  if (priced.length === 0) return { total: null, complete: false };
  return { total: priced.reduce((sum, value) => sum + value, 0), complete: priced.length === values.length };
};

// Which money this is. Paper is simulated; demo/testnet is the broker's practice
// account; anything else in live mode is real money.
export const moneyKind = (summary: AccountSummary | null, executionMode: string) => {
  if (executionMode === 'paper' || summary?.execution_mode === 'paper' || summary?.environment === 'simulated') {
    return { label: 'PAPER', detail: 'Simulated money', className: 'bg-sky-500/15 text-sky-300 border-sky-500/40' };
  }
  const environment = (summary?.environment || '').toLowerCase();
  if (environment === 'demo' || environment === 'testnet' || environment === 'paper') {
    return { label: environment.toUpperCase(), detail: 'Practice money', className: 'bg-amber-500/15 text-amber-300 border-amber-500/40' };
  }
  return { label: 'LIVE', detail: 'Real money', className: 'bg-red-500/20 text-red-300 border-red-500/50' };
};
