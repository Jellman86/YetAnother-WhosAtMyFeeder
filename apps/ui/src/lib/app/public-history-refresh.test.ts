import { afterEach, expect, it, vi } from 'vitest';
import { createPublicHistoryRefresh } from './public-history-refresh';

afterEach(() => vi.useRealTimers());

it('does not starve under continuous updates and retains one in-flight trailing refresh', async () => {
    vi.useFakeTimers();
    let release: () => void = () => undefined;
    const refresh = vi.fn(() => new Promise<void>((resolve) => { release = resolve; }));
    const coordinator = createPublicHistoryRefresh(refresh);
    for (let i = 0; i < 10; i++) {
        coordinator.notify();
        await vi.advanceTimersByTimeAsync(200);
    }
    expect(refresh).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 100; i++) coordinator.notify();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(refresh).toHaveBeenCalledTimes(1);
    release();
    await vi.advanceTimersByTimeAsync(2000);
    expect(refresh).toHaveBeenCalledTimes(2);
    release();
    coordinator.dispose();
    await vi.runAllTimersAsync();
    expect(refresh).toHaveBeenCalledTimes(2);
});

it('cancels pending work when disposed', async () => {
    vi.useFakeTimers();
    const refresh = vi.fn(async () => undefined);
    const coordinator = createPublicHistoryRefresh(refresh);
    coordinator.notify();
    coordinator.dispose();
    await vi.runAllTimersAsync();
    coordinator.notify();
    await vi.runAllTimersAsync();
    expect(refresh).not.toHaveBeenCalled();
});

it('retries failed invalidations with bounded backoff and no unhandled rejection', async () => {
    vi.useFakeTimers();
    const refresh = vi.fn(async () => { throw new Error('503'); });
    const coordinator = createPublicHistoryRefresh(refresh);
    coordinator.notify();
    await vi.advanceTimersByTimeAsync(2000);
    expect(refresh).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(3999);
    expect(refresh).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(refresh).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(8000);
    expect(refresh).toHaveBeenCalledTimes(3);
    await vi.runAllTimersAsync();
    expect(refresh).toHaveBeenCalledTimes(3);
    coordinator.notify();
    await vi.advanceTimersByTimeAsync(2000);
    expect(refresh).toHaveBeenCalledTimes(4);
    coordinator.dispose();
    await vi.runAllTimersAsync();
});

it('stops retries after recovery and disposal', async () => {
    vi.useFakeTimers();
    const refresh = vi.fn().mockRejectedValueOnce(new Error('503')).mockResolvedValue(undefined);
    const coordinator = createPublicHistoryRefresh(refresh);
    coordinator.notify();
    await vi.advanceTimersByTimeAsync(6000);
    expect(refresh).toHaveBeenCalledTimes(2);
    await vi.runAllTimersAsync();
    expect(refresh).toHaveBeenCalledTimes(2);
    coordinator.dispose();
});

it('uses the current rate-budget delay without starving under continuous updates', async () => {
    vi.useFakeTimers();
    let delay = 8000;
    const refresh = vi.fn(async () => undefined);
    const coordinator = createPublicHistoryRefresh(refresh, () => delay);
    for (let i = 0; i < 40; i++) { coordinator.notify(); await vi.advanceTimersByTimeAsync(200); }
    expect(refresh).toHaveBeenCalledTimes(1);
    delay = 2400;
    coordinator.notify();
    await vi.advanceTimersByTimeAsync(2399);
    expect(refresh).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(refresh).toHaveBeenCalledTimes(2);
    coordinator.dispose();
});

it('applies exponential retries relative to the configured guest budget', async () => {
    vi.useFakeTimers();
    const refresh = vi.fn(async () => { throw new Error('503'); });
    const coordinator = createPublicHistoryRefresh(refresh, () => 2400);
    coordinator.notify();
    await vi.advanceTimersByTimeAsync(2400);
    expect(refresh).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(4799);
    expect(refresh).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(refresh).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(9600);
    expect(refresh).toHaveBeenCalledTimes(3);
    await vi.runAllTimersAsync();
    expect(refresh).toHaveBeenCalledTimes(3);
    coordinator.dispose();
});
