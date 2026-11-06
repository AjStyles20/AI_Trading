import { beforeEach, describe, expect, it } from 'vitest';
import {
  describeProposal,
  extractProposals,
  proposalKey,
  readHandledProposals,
  storeHandledProposal,
} from '../aiProposals';

const block = (body: string) => '```astral-action\n' + body + '\n```';

describe('AI proposals', () => {
  beforeEach(() => { window.localStorage.clear(); });

  it('pulls valid actions out of a reply and removes the blocks from the text', () => {
    const reply = `Gold looks strong.\n\n${block('[{"kind":"open_chart","symbol":"gc=f"},{"kind":"price_alert","symbol":"BTC/USDT","direction":"below","price":75000}]')}\n\nYour call.`;

    const { text, proposals } = extractProposals(reply);

    expect(text).toBe('Gold looks strong.\n\nYour call.');
    expect(proposals).toEqual([
      { kind: 'open_chart', symbol: 'GC=F' },
      { kind: 'price_alert', symbol: 'BTC/USDT', direction: 'below', price: 75000 },
    ]);
  });

  it('drops anything that is not one of the three safe kinds or is malformed', () => {
    const reply = [
      block('{"kind":"place_order","symbol":"AAPL","side":"buy","qty":10}'),
      block('{"kind":"disarm_kill_switch"}'),
      block('{"kind":"price_alert","symbol":"AAPL","direction":"sideways","price":1}'),
      block('{"kind":"price_alert","symbol":"AAPL","direction":"above","price":-5}'),
      block('{"kind":"price_alert","symbol":"AAPL","direction":"above","price":"200"}'),
      block('{"kind":"add_watchlist","symbol":"<script>"}'),
      block('not json at all'),
      block('{"kind":"add_watchlist","symbol":"MSFT"}'),
    ].join('\n');

    const { text, proposals } = extractProposals(reply);

    expect(proposals).toEqual([{ kind: 'add_watchlist', symbol: 'MSFT' }]);
    expect(text).toBe('');
  });

  it('keeps at most three suggestions per reply', () => {
    const many = Array.from({ length: 5 }, (_, i) => `{"kind":"add_watchlist","symbol":"SYM${i}"}`);
    expect(extractProposals(block(`[${many.join(',')}]`)).proposals).toHaveLength(3);
  });

  it('leaves ordinary replies and other code blocks untouched', () => {
    const reply = 'Here:\n```python\nprint(1)\n```';
    expect(extractProposals(reply)).toEqual({ text: reply, proposals: [] });
  });

  it('describes each kind in plain words', () => {
    expect(describeProposal({ kind: 'open_chart', symbol: 'AAPL' })).toBe('Open AAPL on the chart');
    expect(describeProposal({ kind: 'add_watchlist', symbol: 'GC=F' })).toBe('Add GC=F to the watchlist');
    expect(describeProposal({ kind: 'price_alert', symbol: 'BTC/USDT', direction: 'above', price: 90000 }))
      .toBe('Alert when BTC/USDT rises to 90,000');
  });

  it('keys handled suggestions by reply text, so a reload remembers them', () => {
    const proposal = { kind: 'add_watchlist', symbol: 'MSFT' } as const;
    const key = proposalKey('reply text', proposal);
    expect(proposalKey('reply text', proposal)).toBe(key);
    expect(proposalKey('other reply', proposal)).not.toBe(key);

    storeHandledProposal(key, 'approved');
    expect(readHandledProposals()[key]).toBe('approved');
  });
});
