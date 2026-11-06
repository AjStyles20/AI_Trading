import { useState } from 'react';

import {
  describeProposal,
  proposalKey,
  readHandledProposals,
  storeHandledProposal,
  type Proposal,
} from '../lib/aiProposals';

type CardState = 'pending' | 'working' | 'approved' | 'dismissed' | 'error';

// Suggestions from an AI reply. Nothing happens until the user clicks Approve.
export default function ProposalCards({
  messageText,
  proposals,
  onApprove,
}: {
  messageText: string;
  proposals: Proposal[];
  onApprove: (proposal: Proposal) => Promise<void>;
}) {
  const [states, setStates] = useState<Record<string, CardState>>(() => {
    const handled = readHandledProposals();
    return Object.fromEntries(proposals.map((p) => {
      const key = proposalKey(messageText, p);
      return [key, handled[key] ?? 'pending'];
    }));
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  if (proposals.length === 0) return null;

  const approve = async (proposal: Proposal, key: string) => {
    setStates((current) => ({ ...current, [key]: 'working' }));
    try {
      await onApprove(proposal);
      storeHandledProposal(key, 'approved');
      setStates((current) => ({ ...current, [key]: 'approved' }));
    } catch (err) {
      setErrors((current) => ({ ...current, [key]: err instanceof Error ? err.message : 'It could not be done.' }));
      setStates((current) => ({ ...current, [key]: 'error' }));
    }
  };

  const dismiss = (key: string) => {
    storeHandledProposal(key, 'dismissed');
    setStates((current) => ({ ...current, [key]: 'dismissed' }));
  };

  return (
    <div className="mt-2 space-y-1.5" aria-label="AI suggestions">
      {proposals.map((proposal) => {
        const key = proposalKey(messageText, proposal);
        const state = states[key] ?? 'pending';
        return (
          <div key={key} data-testid="proposal-card" data-state={state} className="rounded-lg border border-[#a55eea]/40 bg-[#a55eea]/5 px-2 py-1.5 text-[11px]">
            <div className="text-[9px] uppercase tracking-widest text-[#a55eea]">Suggestion · needs your approval</div>
            <div className="text-gray-200">{describeProposal(proposal)}</div>
            {state === 'pending' || state === 'error' ? (
              <div className="mt-1 flex gap-2">
                <button type="button" onClick={() => void approve(proposal, key)} className="px-2 py-0.5 rounded bg-[#a55eea] text-white hover:bg-[#b87ef7]">
                  Approve
                </button>
                <button type="button" onClick={() => dismiss(key)} className="px-2 py-0.5 rounded border border-[#2a2a35] text-gray-400 hover:text-gray-200">
                  Dismiss
                </button>
              </div>
            ) : (
              <div className="mt-1 text-[10px] text-gray-500">
                {state === 'working' ? 'Working...' : state === 'approved' ? 'Done' : 'Dismissed'}
              </div>
            )}
            {state === 'error' && <div role="alert" className="mt-1 text-[10px] text-red-400">{errors[key]}</div>}
          </div>
        );
      })}
    </div>
  );
}
