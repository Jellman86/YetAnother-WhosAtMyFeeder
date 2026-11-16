import { describe, expect, it, vi } from 'vitest';
import { createSharedRead } from './shared-read';

function deferred<T>() {
    let resolve!: (value: T) => void;
    let reject!: (error: unknown) => void;
    const promise = new Promise<T>((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return { promise, resolve, reject };
}

describe('createSharedRead', () => {
    it('sends one request for callers that ask while it is in flight', async () => {
        const pending = deferred<string>();
        const read = vi.fn(() => pending.promise);
        const shared = createSharedRead(read, { shareForMs: 0 });

        const first = shared.read();
        const second = shared.read();
        pending.resolve('reading');

        await expect(first).resolves.toBe('reading');
        await expect(second).resolves.toBe('reading');
        expect(read).toHaveBeenCalledTimes(1);
    });

    it('hands a reading that has just arrived to a caller who asks within the share window', async () => {
        let now = 1_000;
        const read = vi.fn(async () => `reading at ${now}`);
        const shared = createSharedRead(read, { shareForMs: 3_000, now: () => now });

        await shared.read();
        now += 2_999;
        await expect(shared.read()).resolves.toBe('reading at 1000');
        expect(read).toHaveBeenCalledTimes(1);
    });

    it('reads again once the share window has passed', async () => {
        let now = 1_000;
        const read = vi.fn(async () => `reading at ${now}`);
        const shared = createSharedRead(read, { shareForMs: 3_000, now: () => now });

        await shared.read();
        now += 3_000;
        await expect(shared.read()).resolves.toBe('reading at 4000');
        expect(read).toHaveBeenCalledTimes(2);
    });

    it('never keeps a failure: the next caller asks the server again', async () => {
        const read = vi.fn()
            .mockRejectedValueOnce(new Error('offline'))
            .mockResolvedValueOnce('reading');
        const shared = createSharedRead(read, { shareForMs: 60_000 });

        await expect(shared.read()).rejects.toThrow('offline');
        await expect(shared.read()).resolves.toBe('reading');
        expect(read).toHaveBeenCalledTimes(2);
    });

    it('drops a kept reading when invalidated, so a change is read straight away', async () => {
        let value = 'before';
        const read = vi.fn(async () => value);
        const shared = createSharedRead(read, { shareForMs: 60_000 });

        await shared.read();
        value = 'after';
        shared.invalidate();
        await expect(shared.read()).resolves.toBe('after');
    });

    it('does not hand an in-flight request that began before an invalidation to a later caller', async () => {
        const first = deferred<string>();
        const read = vi.fn()
            .mockImplementationOnce(() => first.promise)
            .mockResolvedValueOnce('after the change');
        const shared = createSharedRead(read, { shareForMs: 60_000 });

        const early = shared.read();
        shared.invalidate();
        const late = shared.read();
        first.resolve('before the change');

        await expect(early).resolves.toBe('before the change');
        await expect(late).resolves.toBe('after the change');
        // The early answer is not kept either: it was read before the change.
        await expect(shared.read()).resolves.toBe('after the change');
        expect(read).toHaveBeenCalledTimes(2);
    });

    it('lets one caller stop waiting without cancelling the request for the others', async () => {
        const pending = deferred<string>();
        const read = vi.fn(() => pending.promise);
        const shared = createSharedRead(read, { shareForMs: 0 });
        const controller = new AbortController();

        const leaving = shared.read(controller.signal);
        const staying = shared.read();
        controller.abort();
        pending.resolve('reading');

        await expect(leaving).rejects.toMatchObject({ name: 'AbortError' });
        await expect(staying).resolves.toBe('reading');
        expect(read).toHaveBeenCalledTimes(1);
    });

    it('refuses at once for a caller whose signal is already aborted, without a request', async () => {
        const read = vi.fn(async () => 'reading');
        const shared = createSharedRead(read, { shareForMs: 0 });
        const controller = new AbortController();
        controller.abort();

        await expect(shared.read(controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
        expect(read).not.toHaveBeenCalled();
    });
});
