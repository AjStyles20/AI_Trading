import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import BackupsSection from '../BackupsSection';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    isAxiosError: (error: unknown) => Boolean((error as { isAxiosError?: boolean })?.isAxiosError),
  },
}));

const get = vi.mocked(axios.get);
const post = vi.mocked(axios.post);

describe('BackupsSection', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  const renderSection = async () => {
    render(<BackupsSection />);
    await act(async () => {});
  };

  it('lists existing backups and where they are kept', async () => {
    get.mockResolvedValue({ data: {
      folder: 'C:\\Users\\me\\AppData\\Roaming\\Astral\\backups',
      items: [{ name: 'astral-20261105-101500.db', size_bytes: 70_000, created: '2026-11-05 10:15:00' }],
    } });
    await renderSection();

    expect(screen.getByTestId('backup-item')).toHaveTextContent('2026-11-05 10:15:0068 KB');
    expect(screen.getByText('C:\\Users\\me\\AppData\\Roaming\\Astral\\backups')).toBeInTheDocument();
    expect(screen.getByText(/API keys \(in your system's credential store\) and the AI's long-term memory are not included/)).toBeInTheDocument();
  });

  it('backs up on request and shows the new backup first', async () => {
    get.mockResolvedValue({ data: { folder: 'f', items: [] } });
    post.mockResolvedValue({ data: { folder: 'f', backup: { name: 'astral-20261105-110000.db', size_bytes: 2_000_000, created: '2026-11-05 11:00:00' } } });
    await renderSection();
    expect(screen.getByText('No backups yet.')).toBeInTheDocument();

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Back up now' })); });

    expect(post).toHaveBeenCalledWith(expect.stringContaining('/api/backups'));
    expect(screen.getByText('Saved astral-20261105-110000.db')).toBeInTheDocument();
    expect(screen.getByTestId('backup-item')).toHaveTextContent('1.9 MB');
  });

  it('shows why a backup failed', async () => {
    get.mockResolvedValue({ data: { folder: 'f', items: [] } });
    post.mockRejectedValue({ isAxiosError: true, response: { data: { detail: 'Backup failed: OSError' } } });
    await renderSection();

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Back up now' })); });

    expect(screen.getByRole('alert')).toHaveTextContent('Backup failed: OSError');
  });
});
