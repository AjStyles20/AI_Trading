import { normalizeSymbol } from './watchlist';

// Actions the AI may suggest in a reply, as a fenced ```astral-action block of
// JSON. They are shown as cards and only run when the user clicks Approve.
// None can place, change or cancel an order. Model output is untrusted text,
// so every field is validated like user input; anything else is dropped.

export type Proposal =
  | { kind: 'open_chart'; symbol: string }
  | { kind: 'add_watchlist'; symbol: string }
  | { kind: 'price_alert'; symbol: string; direction: 'above' | 'below'; price: number };

export const MAX_PROPOSALS_PER_REPLY = 3;

const BLOCK = /```astral-action[^\n]*\n([\s\S]*?)```/g;

const toProposal = (raw: unknown): Proposal | null => {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const item = raw as Record<string, unknown>;
  const symbol = typeof item.symbol === 'string' ? normalizeSymbol(item.symbol) : null;
  if (!symbol) return null;
  if (item.kind === 'open_chart' || item.kind === 'add_watchlist') return { kind: item.kind, symbol };
  if (item.kind === 'price_alert') {
    const price = typeof item.price === 'number' ? item.price : NaN;
    if ((item.direction === 'above' || item.direction === 'below') && Number.isFinite(price) && price > 0) {
      return { kind: 'price_alert', symbol, direction: item.direction, price };
    }
  }
  return null;
};

// The reply without its action blocks, and the valid proposals they held.
export const extractProposals = (text: string): { text: string; proposals: Proposal[] } => {
  const proposals: Proposal[] = [];
  const cleaned = text.replace(BLOCK, (_match, body: string) => {
    try {
      const parsed: unknown = JSON.parse(body);
      for (const raw of Array.isArray(parsed) ? parsed : [parsed]) {
        const proposal = toProposal(raw);
        if (proposal) proposals.push(proposal);
      }
    } catch {
      // Not JSON: drop the block, show nothing for it.
    }
    return '';
  });
  return { text: cleaned.replace(/\n{3,}/g, '\n\n').trim(), proposals: proposals.slice(0, MAX_PROPOSALS_PER_REPLY) };
};

export const describeProposal = (proposal: Proposal): string => {
  if (proposal.kind === 'open_chart') return `Open ${proposal.symbol} on the chart`;
  if (proposal.kind === 'add_watchlist') return `Add ${proposal.symbol} to the watchlist`;
  const level = proposal.price.toLocaleString(undefined, { maximumFractionDigits: 8 });
  return `Alert when ${proposal.symbol} ${proposal.direction === 'above' ? 'rises to' : 'falls to'} ${level}`;
};

// A key that survives reloads: history messages get new ids each time, so the
// key comes from the reply's text and the proposal itself.
export const proposalKey = (messageText: string, proposal: Proposal): string => {
  let hash = 5381;
  for (let i = 0; i < messageText.length; i += 1) hash = ((hash * 33) ^ messageText.charCodeAt(i)) >>> 0;
  return `${hash.toString(36)}|${JSON.stringify(proposal)}`;
};

const HANDLED_KEY = 'astral.chat.handledProposals';
const MAX_HANDLED = 500;

export const readHandledProposals = (): Record<string, 'approved' | 'dismissed'> => {
  try {
    const stored = JSON.parse(window.localStorage.getItem(HANDLED_KEY) ?? '{}');
    return stored && typeof stored === 'object' && !Array.isArray(stored) ? stored : {};
  } catch {
    return {};
  }
};

export const storeHandledProposal = (key: string, state: 'approved' | 'dismissed') => {
  try {
    const entries = Object.entries({ ...readHandledProposals(), [key]: state }).slice(-MAX_HANDLED);
    window.localStorage.setItem(HANDLED_KEY, JSON.stringify(Object.fromEntries(entries)));
  } catch {
    // Storage unavailable: the choice still applies for this session.
  }
};
