import { describe, expect, it } from 'vitest';
import { apiFetch, apiFetchJson, mapGuarded } from '../api/core';
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
        const guardedRead = () => mapGuarded(apiFetchJson<{ ok: boolean }>('/api/status'), (body) => body.ok);
        const reader = createRetryingReader({ read: guardedRead, active });
        const follower = followRevisions(guardedRead, null);

        // Checked by the compiler only; never called, so nothing is requested.
        const refused = (): void => {
        // @ts-expect-error a bare fetch releases nothing at the body
        createRetryingReader({ read: () => fetch('/api/status').then((response) => response.ok), active });
        // @ts-expect-error apiFetch's timeout and cancel end at the headers
        createRetryingReader({ read: () => apiFetch('/api/status').then((response) => response.ok), active });
        // @ts-expect-error an async function is a plain promise, whatever it awaits
        followRevisions(async () => (await apiFetchJson<{ ok: boolean }>('/api/status')).ok, null);
        // @ts-expect-error a step after a guarded read may not start an unguarded request of its own
        mapGuarded(apiFetchJson<{ ok: boolean }>('/api/status'), () => apiFetch('/api/other'));
        };
        expect(typeof refused).toBe('function');

        reader.cancel();
        follower.stop();
    });
});
