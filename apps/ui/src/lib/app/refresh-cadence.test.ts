import { describe, expect, it } from 'vitest';

import { REFRESH_CADENCE_MS, readAtMostEvery } from './refresh-cadence';

describe('background refresh cadence', () => {
    // What the polls do at these rates is exercised with timers in visible-poll.test.ts and
    // server_jobs.test.ts; this only pins the relations between the rates.
    it('follows active work closely and idle work slowly', () => {
        expect(REFRESH_CADENCE_MS.serverJobsActive).toBeLessThan(REFRESH_CADENCE_MS.serverJobsIdle);
        expect(REFRESH_CADENCE_MS.analysisQueueActive).toBeLessThan(REFRESH_CADENCE_MS.analysisQueueIdle);
        expect(REFRESH_CADENCE_MS.providerWarningChecking).toBeLessThan(REFRESH_CADENCE_MS.providerWarning);
    });
});

describe('readAtMostEvery', () => {
    it('reads once per interval and answers skipped calls with the last value', async () => {
        let clock = 0;
        let reads = 0;
        const read = readAtMostEvery(async () => ++reads, 1000, () => clock);

        expect(await read()).toBe(1);
        clock = 999;
        expect(await read()).toBe(1);
        clock = 1000;
        expect(await read()).toBe(2);
        expect(reads).toBe(2);
    });

    it('shares one request between overlapping callers', async () => {
        let reads = 0;
        const read = readAtMostEvery(async () => ++reads, 1000, () => 0);
        expect(await Promise.all([read(), read()])).toEqual([1, 1]);
    });

    it('reads again after a failure instead of remembering it', async () => {
        let reads = 0;
        const read = readAtMostEvery(async () => {
            reads += 1;
            if (reads === 1) throw new Error('unreachable');
            return reads;
        }, 1000, () => 0);

        await expect(read()).rejects.toThrow('unreachable');
        expect(await read()).toBe(2);
    });
});
