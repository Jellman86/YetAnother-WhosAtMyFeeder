import { describe, expect, it } from 'vitest';
import { createSlotGate } from './concurrency';

function deferred<T = void>() {
    let resolve!: (v: T) => void;
    let reject!: (e: unknown) => void;
    const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
}

describe('createSlotGate', () => {
    it('never runs more than the limit at once and admits the rest in order', async () => {
        const gate = createSlotGate(3);
        const holds = Array.from({ length: 6 }, () => deferred());
        const started: number[] = [];
        const runs = holds.map((h, i) => gate.run(async () => { started.push(i); await h.promise; return i; }));
        await Promise.resolve();
        expect(started).toEqual([0, 1, 2]);
        expect(gate.active).toBe(3);

        holds[1].resolve();
        await runs[1];
        await Promise.resolve();
        expect(started).toEqual([0, 1, 2, 3]);
        expect(gate.active).toBe(3);

        for (const h of holds) h.resolve();
        expect(await Promise.all(runs)).toEqual([0, 1, 2, 3, 4, 5]);
        expect(gate.active).toBe(0);
    });

    it('releases the slot when the work throws, so a failure cannot wedge the gate', async () => {
        const gate = createSlotGate(1);
        await expect(gate.run(async () => { throw new Error('boom'); })).rejects.toThrow('boom');
        expect(gate.active).toBe(0);
        expect(await gate.run(async () => 'after')).toBe('after');
    });

    it('refuses a limit that would admit nothing', () => {
        expect(() => createSlotGate(0)).toThrow(RangeError);
    });
});
