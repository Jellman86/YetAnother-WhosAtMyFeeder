import { describe, expect, it } from 'vitest';
import { apiFetch, apiFetchJson, chainGuarded, guardedValue, mapGuarded, type Guarded } from '../api/core';
import { createRetryingReader } from './retrying-reader';
import { followRevisions } from './revision-follower';

/**
 * The readers take only guarded reads, so a read whose timeout and cancel stop at the headers is
 * refused when the code is checked (`npm run check`), not found later in a stalled browser. Each
 * `@ts-expect-error` below fails the check if that unguarded read is ever accepted.
 */
describe('readers refuse an unguarded read', () => {
    it('type-checks only reads built from the guarded client', () => {
        const active = (): boolean => false;
        const guardedRead = () => mapGuarded(apiFetchJson<{ ok: boolean }>('/api/status', { timeoutMs: 10_000 }), (body) => body.ok);
        const reader = createRetryingReader({ read: guardedRead, active });
        const follower = followRevisions(guardedRead, null);

        // Checked by the compiler only; never called, so nothing is requested.
        const refused = (): void => {
        // @ts-expect-error a bare fetch releases nothing at the body
        createRetryingReader({ read: () => fetch('/api/status').then((response) => response.ok), active });
        // @ts-expect-error apiFetch's timeout and cancel end at the headers
        createRetryingReader({ read: () => apiFetch('/api/status').then((response) => response.ok), active });
        // @ts-expect-error an async function is a plain promise, whatever it awaits
        followRevisions(async () => (await apiFetchJson<{ ok: boolean }>('/api/status', { timeoutMs: 10_000 })).ok, null);
        // @ts-expect-error a step after a guarded read may not start an unguarded request of its own
        mapGuarded(apiFetchJson<{ ok: boolean }>('/api/status', { timeoutMs: 10_000 }), () => apiFetch('/api/other'));
        // @ts-expect-error a guarded read has a deadline, so one must be given
        apiFetchJson('/api/status');
        // @ts-expect-error widening the step's result to unknown does not let a request through
        mapGuarded<undefined, unknown>(guardedValue(undefined), () => fetch('/api/other'));
        // @ts-expect-error nor does widening it to void, which a promise-returning callback satisfies
        mapGuarded<undefined, void>(guardedValue(undefined), () => fetch('/api/other'));
        // @ts-expect-error a failure handler may not start a request either
        mapGuarded<boolean, unknown>(guardedValue(true), (ok) => ok, () => fetch('/api/other'));
        // @ts-expect-error a settled value is not a request in flight
        guardedValue<unknown>(fetch('/api/other'));
        // @ts-expect-error nor when widened to void
        guardedValue<void>(fetch('/api/other'));
        };
        expect(typeof refused).toBe('function');

        reader.cancel();
        follower.stop();
    });
});

/** A cast or an `any` can still get a promise past the compiler; the combinators refuse it when it runs. */
describe('the combinators refuse a promise at run time', () => {
    const promise = (): never => Promise.resolve(true) as never;
    const smuggled = <T>(value: unknown): T => value as T;

    it('as a step after a guarded read', async () => {
        await expect(mapGuarded(guardedValue(1), () => promise())).rejects.toBeInstanceOf(TypeError);
    });

    it('as a failure handler', async () => {
        const failed: Guarded<number> = mapGuarded(guardedValue(1), () => {
            throw new Error('HTTP 500');
        });
        await expect(mapGuarded(failed, (value) => value, () => promise())).rejects.toBeInstanceOf(TypeError);
        await expect(chainGuarded(failed, () => guardedValue(2), () => promise())).rejects.toBeInstanceOf(TypeError);
    });

    it('as a settled value', async () => {
        await expect(guardedValue(smuggled<number>(Promise.resolve(1)))).rejects.toBeInstanceOf(TypeError);
        await expect(guardedValue(smuggled<number>({ then: () => undefined }))).rejects.toBeInstanceOf(TypeError);
    });

    /** `then` reads as nothing to the check, then as a function when the promise resolves it. */
    function changingThen(): never {
        let reads = 0;
        return {
            get then() {
                reads += 1;
                return reads === 1 ? undefined : (resolve: (value: unknown) => void) => resolve('smuggled');
            }
        } as never;
    }

    it('when its `then` is a getter that changes between reads, on every combinator', async () => {
        const failed: Guarded<number> = mapGuarded(guardedValue(1), () => {
            throw new Error('HTTP 500');
        });
        await expect(mapGuarded(guardedValue(1), () => changingThen())).rejects.toBeInstanceOf(TypeError);
        await expect(mapGuarded(failed, (value) => value, () => changingThen())).rejects.toBeInstanceOf(TypeError);
        await expect(chainGuarded(failed, () => guardedValue(2), () => changingThen())).rejects.toBeInstanceOf(TypeError);
        await expect(guardedValue(smuggled<number>(changingThen()))).rejects.toBeInstanceOf(TypeError);
    });

    it('when the getter is inherited, without ever calling it', async () => {
        let calls = 0;
        const parent = {
            get then() {
                calls += 1;
                return undefined;
            }
        };
        await expect(guardedValue(smuggled<number>(Object.create(parent)))).rejects.toBeInstanceOf(TypeError);
        expect(calls).toBe(0);
    });

    it('lets plain values through, undefined included', async () => {
        await expect(mapGuarded(guardedValue(1), (value) => value + 1)).resolves.toBe(2);
        await expect(guardedValue(undefined)).resolves.toBeUndefined();
        await expect(guardedValue({ then: 'not a function' })).resolves.toEqual({ then: 'not a function' });
    });
});
