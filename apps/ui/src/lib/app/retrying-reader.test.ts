import { afterEach, describe, expect, it, vi } from 'vitest';
import { asGuarded } from '../test-support/guarded';
import { READ_DEADLINE_MS, READ_RETRY_MS, createRetryingReader } from './retrying-reader';

afterEach(() => vi.useRealTimers());

describe('createRetryingReader', () => {
    it('retries a failed read with a growing wait, capped, until one succeeds', async () => {
        vi.useFakeTimers();
        const read = vi.fn<() => Promise<boolean>>()
            .mockResolvedValueOnce(false)
            .mockRejectedValueOnce(new Error('HTTP 502'))
            .mockResolvedValue(true);
        const reader = createRetryingReader({ read: () => asGuarded(read()), active: () => true });
        reader.request();
        await vi.advanceTimersByTimeAsync(0);
        expect(read).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(READ_RETRY_MS[0]);
        expect(read).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(READ_RETRY_MS[1]);
        expect(read).toHaveBeenCalledTimes(3);
        await vi.advanceTimersByTimeAsync(10 * READ_RETRY_MS[READ_RETRY_MS.length - 1]);
        expect(read).toHaveBeenCalledTimes(3);
    });

    it('never waits longer than the last step between retries', async () => {
        vi.useFakeTimers();
        const read = vi.fn(async () => false);
        const reader = createRetryingReader({ read: () => asGuarded(read()), active: () => true });
        reader.request();
        const total = READ_RETRY_MS.reduce((sum, wait) => sum + wait, 0) + 3 * READ_RETRY_MS[READ_RETRY_MS.length - 1];
        await vi.advanceTimersByTimeAsync(total);
        expect(read).toHaveBeenCalledTimes(1 + READ_RETRY_MS.length + 3);
        reader.cancel();
    });

    it('queues one more read for a request made while a read is in flight', async () => {
        let release: (ok: boolean) => void = () => undefined;
        const read = vi.fn<() => Promise<boolean>>()
            .mockImplementationOnce(() => new Promise((done) => { release = done; }))
            .mockResolvedValue(true);
        const reader = createRetryingReader({ read: () => asGuarded(read()), active: () => true });
        reader.request();
        reader.request();
        reader.request();
        release(true);
        await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(2));
        await Promise.resolve();
        expect(read).toHaveBeenCalledTimes(2);
    });

    it('stops retrying once it is no longer wanted, and ignores a late result after cancel', async () => {
        vi.useFakeTimers();
        let wanted = true;
        let release: (ok: boolean) => void = () => undefined;
        const read = vi.fn<() => Promise<boolean>>()
            .mockResolvedValueOnce(false)
            .mockImplementationOnce(() => new Promise((done) => { release = done; }))
            .mockResolvedValue(false);
        const reader = createRetryingReader({ read: () => asGuarded(read()), active: () => wanted });
        reader.request();
        await vi.advanceTimersByTimeAsync(READ_RETRY_MS[0]);
        expect(read).toHaveBeenCalledTimes(2);
        reader.cancel();
        release(false);
        await vi.advanceTimersByTimeAsync(10 * READ_RETRY_MS[READ_RETRY_MS.length - 1]);
        expect(read).toHaveBeenCalledTimes(2);

        wanted = false;
        reader.request();
        await vi.advanceTimersByTimeAsync(10 * READ_RETRY_MS[READ_RETRY_MS.length - 1]);
        // Asked again after the cancel, it reads once; with nobody wanting it any more it does not retry.
        expect(read).toHaveBeenCalledTimes(3);
    });
});

describe('createRetryingReader after a failure', () => {
    it('folds new requests into the read at the retry deadline instead of reading at once', async () => {
        vi.useFakeTimers();
        const read = vi.fn(async () => false);
        const reader = createRetryingReader({ read: () => asGuarded(read()), active: () => true });
        reader.request();
        await vi.advanceTimersByTimeAsync(0);
        for (let second = 0; second < 20; second += 1) {
            reader.request();
            await vi.advanceTimersByTimeAsync(1_000);
        }
        // 0 s, then 5 s and 20 s on the schedule: three reads in twenty seconds, never twenty-one.
        expect(read).toHaveBeenCalledTimes(3);
        reader.cancel();
    });

    it('gives up on a read that outlives its deadline, aborts it and retries on the backoff', async () => {
        vi.useFakeTimers();
        const signals: AbortSignal[] = [];
        // Never settles, whatever its signal does: the reader's own deadline is what frees it.
        const read = vi.fn((signal: AbortSignal) => {
            signals.push(signal);
            return asGuarded(new Promise<boolean>(() => undefined));
        });
        const reader = createRetryingReader({ read, active: () => true });
        reader.request();
        await vi.advanceTimersByTimeAsync(READ_DEADLINE_MS - 1);
        expect(signals[0]?.aborted).toBe(false);
        await vi.advanceTimersByTimeAsync(1);
        expect(signals[0]?.aborted).toBe(true);
        reader.request();
        await vi.advanceTimersByTimeAsync(READ_RETRY_MS[0] - 1);
        expect(read).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(1);
        expect(read).toHaveBeenCalledTimes(2);
        reader.cancel();
    });
});
