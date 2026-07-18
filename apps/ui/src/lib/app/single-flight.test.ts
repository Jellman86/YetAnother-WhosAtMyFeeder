import { describe, expect, it, vi } from 'vitest';

import { createSingleFlightRunner } from './single-flight';

describe('createSingleFlightRunner', () => {
    it('shares one in-flight task across concurrent triggers', async () => {
        let resolveTask!: () => void;
        const task = vi.fn(() => new Promise<void>((resolve) => {
            resolveTask = resolve;
        }));
        const run = createSingleFlightRunner(task);

        const first = run();
        const second = run();

        expect(task).toHaveBeenCalledTimes(1);
        expect(second).toBe(first);
        resolveTask();
        await first;
    });

    it('allows another run after the active task settles', async () => {
        const task = vi.fn().mockResolvedValue(undefined);
        const run = createSingleFlightRunner(task);

        await run();
        await run();

        expect(task).toHaveBeenCalledTimes(2);
    });

    it('releases the guard after a failed task', async () => {
        const task = vi.fn()
            .mockRejectedValueOnce(new Error('temporary failure'))
            .mockResolvedValueOnce(undefined);
        const run = createSingleFlightRunner(task);

        await expect(run()).rejects.toThrow('temporary failure');
        await expect(run()).resolves.toBeUndefined();

        expect(task).toHaveBeenCalledTimes(2);
    });
});
