import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ProposalCards from '../ProposalCards';
import type { Proposal } from '../../lib/aiProposals';

const alert: Proposal = { kind: 'price_alert', symbol: 'BTC/USDT', direction: 'below', price: 75000 };
const chart: Proposal = { kind: 'open_chart', symbol: 'AAPL' };

describe('ProposalCards', () => {
  it('does nothing until approved, then runs the action once and remembers it', async () => {
    const onApprove = vi.fn(async () => {});
    const { unmount } = render(<ProposalCards messageText="reply" proposals={[alert, chart]} onApprove={onApprove} />);

    expect(screen.getAllByTestId('proposal-card')).toHaveLength(2);
    expect(screen.getByText('Alert when BTC/USDT falls to 75,000')).toBeInTheDocument();
    expect(onApprove).not.toHaveBeenCalled();

    await act(async () => { fireEvent.click(screen.getAllByRole('button', { name: 'Approve' })[0]); });
    expect(onApprove).toHaveBeenCalledWith(alert);
    expect(screen.getAllByTestId('proposal-card')[0]).toHaveAttribute('data-state', 'approved');
    unmount();

    // After a reload the same reply shows it as done, so it can't be repeated.
    render(<ProposalCards messageText="reply" proposals={[alert, chart]} onApprove={onApprove} />);
    expect(screen.getAllByTestId('proposal-card')[0]).toHaveAttribute('data-state', 'approved');
    expect(screen.getAllByRole('button', { name: 'Approve' })).toHaveLength(1);
  });

  it('dismisses without running anything', () => {
    const onApprove = vi.fn(async () => {});
    render(<ProposalCards messageText="another reply" proposals={[chart]} onApprove={onApprove} />);

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));

    expect(onApprove).not.toHaveBeenCalled();
    expect(screen.getByTestId('proposal-card')).toHaveAttribute('data-state', 'dismissed');
  });

  it('shows why an approved action failed and lets the user try again', async () => {
    const onApprove = vi.fn(async () => { throw new Error('Could not add the alert: offline'); });
    render(<ProposalCards messageText="third reply" proposals={[alert]} onApprove={onApprove} />);

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Approve' })); });

    expect(screen.getByRole('alert')).toHaveTextContent('Could not add the alert: offline');
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
  });

  it('renders nothing when there are no suggestions', () => {
    const { container } = render(<ProposalCards messageText="x" proposals={[]} onApprove={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
