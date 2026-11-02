import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import TradingSessionPanel from '../TradingSessionPanel';

const config = { symbol: 'BTC/USDT', interval: '1h', broker_id: 'paper', execution_mode: 'paper' };

const renderPanel = (overrides = {}) => {
  const onArm = vi.fn();
  const onStop = vi.fn();
  render(
    <TradingSessionPanel
      isRunning={false}
      config={config}
      killSwitchArmed={true}
      isArming={false}
      error=""
      onArm={onArm}
      onStop={onStop}
      {...overrides}
    />,
  );
  return { onArm, onStop };
};

describe('TradingSessionPanel', () => {
  it('never offers a way to disarm the kill switch', () => {
    for (const killSwitchArmed of [true, false, null]) {
      const { unmount } = render(
        <TradingSessionPanel isRunning config={config} killSwitchArmed={killSwitchArmed} isArming={false} error="" onArm={vi.fn()} onStop={vi.fn()} />,
      );
      expect(screen.queryByRole('button', { name: /disarm/i })).toBeNull();
      unmount();
    }
  });

  it('offers arming while disarmed and calls it with one click', () => {
    const { onArm } = renderPanel({ killSwitchArmed: false });

    expect(screen.getByTestId('kill-switch-state')).toHaveTextContent('KILL SWITCH DISARMED');
    fireEvent.click(screen.getByRole('button', { name: 'Arm kill switch' }));
    expect(onArm).toHaveBeenCalledTimes(1);
  });

  it('shows an unreadable state as unknown, never as safe, and still offers arming', () => {
    renderPanel({ killSwitchArmed: null });

    expect(screen.getByTestId('kill-switch-state')).toHaveTextContent('KILL SWITCH UNKNOWN');
    expect(screen.getByText(/could not be read/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Arm kill switch' })).toBeInTheDocument();
  });

  it('says it is still checking before the first read, not that the read failed', () => {
    renderPanel({ killSwitchArmed: undefined });

    expect(screen.getByTestId('kill-switch-state')).toHaveTextContent('KILL SWITCH CHECKING');
    expect(screen.queryByText(/could not be read/)).toBeNull();
    expect(screen.getByRole('button', { name: 'Arm kill switch' })).toBeInTheDocument();
  });

  it('needs no arm button once armed, and says what the loop does while armed', () => {
    renderPanel({ killSwitchArmed: true, isRunning: true });

    expect(screen.queryByRole('button', { name: 'Arm kill switch' })).toBeNull();
    expect(screen.getByText(/only observing and reconciling/)).toBeInTheDocument();
  });

  it('shows what is running with stop, and marks live sessions', () => {
    const { onStop } = renderPanel({ isRunning: true, config: { ...config, execution_mode: 'live' } });

    expect(screen.getByTestId('session-state')).toHaveTextContent('RUNNING');
    expect(screen.getByTestId('session-details')).toHaveTextContent('BTC/USDT · 1h · paper · LIVE');
    fireEvent.click(screen.getByRole('button', { name: 'Stop session' }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it('hides stop and the old session details while idle', () => {
    renderPanel({ isRunning: false });

    expect(screen.getByTestId('session-state')).toHaveTextContent('IDLE');
    expect(screen.queryByRole('button', { name: 'Stop session' })).toBeNull();
    expect(screen.queryByTestId('session-details')).toBeNull();
  });
});
