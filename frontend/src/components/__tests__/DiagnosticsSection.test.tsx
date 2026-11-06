import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import DiagnosticsSection from '../DiagnosticsSection';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    isAxiosError: (error: unknown) => Boolean((error as { isAxiosError?: boolean })?.isAxiosError),
  },
}));

const get = vi.mocked(axios.get);

describe('DiagnosticsSection', () => {
  beforeEach(() => { get.mockReset(); });

  it('shows the whole report before copying, and asks nothing until clicked', async () => {
    get.mockResolvedValue({ data: { report: 'Astral AI diagnostics report\n- Kill switch armed: True\n' } });
    render(<DiagnosticsSection />);
    expect(get).not.toHaveBeenCalled();

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Create report' })); });

    expect(get).toHaveBeenCalledWith(expect.stringContaining('/api/diagnostics/report'));
    expect((screen.getByLabelText('Diagnostics report') as HTMLTextAreaElement).value).toContain('Kill switch armed: True');
    expect(screen.getByRole('button', { name: 'Copy report' })).toBeInTheDocument();
  });

  it('says why a report could not be created', async () => {
    get.mockRejectedValue({ isAxiosError: true, response: { data: { detail: 'database is locked' } } });
    render(<DiagnosticsSection />);

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Create report' })); });

    expect(screen.getByRole('alert')).toHaveTextContent('Could not create the report: database is locked');
  });
});
