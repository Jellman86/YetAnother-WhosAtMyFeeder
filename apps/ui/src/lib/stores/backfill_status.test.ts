import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { BackfillJobStatus } from '../api/backfill';
import { jobProgressStore } from './job_progress.svelte';
import { BackfillStatusStore } from './backfill_status.svelte';

describe('BackfillStatusStore', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        jobProgressStore.clearAll();
    });

    afterEach(() => {
        vi.useRealTimers();
        jobProgressStore.clearAll();
    });

    it('settles stale synthetic backfill jobs when fresh status is empty', async () => {
        jobProgressStore.upsertRunning({
            id: 'backfill:detections:old-job',
            kind: 'backfill',
            title: 'Detection Backfill',
            current: 0,
            total: 23,
            source: 'poll'
        });
        await vi.advanceTimersByTimeAsync(1001);
        jobProgressStore.markStale(0);

        const store = new BackfillStatusStore({
            fetchBackfillStatus: async () => null,
            hasOwnerAccess: () => true
        });

        await store.refresh();

        expect(jobProgressStore.activeJobs.find((job) => job.id === 'backfill:detections:old-job')).toBeUndefined();
        const completed = jobProgressStore.historyJobs.find((job) => job.id === 'backfill:detections:old-job');
        expect(completed?.status).toBe('completed');
        expect(completed?.current).toBe(23);
        expect(completed?.total).toBe(23);
    });

    it('keeps scoped totals stable when a running backfill status temporarily reports total as zero', async () => {
        const statuses = new Map<string, BackfillJobStatus | null>([
            ['detections', {
                id: 'job-1',
                kind: 'backfill',
                status: 'running',
                processed: 0,
                total: 23,
                new_detections: 0,
                skipped: 0,
                errors: 0,
                message: 'Working'
            }],
            ['weather', null]
        ]);

        const store = new BackfillStatusStore({
            fetchBackfillStatus: async (kind) => statuses.get(kind) ?? null,
            hasOwnerAccess: () => true
        });

        await store.refresh();
        let running = jobProgressStore.activeJobs.find((job) => job.id === 'backfill:detections:job-1');
        expect(running?.total).toBe(23);

        statuses.set('detections', {
            id: 'job-1',
            kind: 'backfill',
            status: 'running',
            processed: 0,
            total: 0,
            new_detections: 0,
            skipped: 0,
            errors: 0,
            message: 'Still working'
        });

        await store.refresh();

        running = jobProgressStore.activeJobs.find((job) => job.id === 'backfill:detections:job-1');
        expect(running?.status).toBe('running');
        expect(running?.total).toBe(23);
    });

    it('continues syncing the healthy backfill kind when the other poll request fails', async () => {
        const store = new BackfillStatusStore({
            fetchBackfillStatus: async (kind) => {
                if (kind === 'weather') {
                    throw new Error('weather status unavailable');
                }
                return {
                    id: 'job-healthy',
                    kind: 'backfill',
                    status: 'running',
                    processed: 3,
                    total: 10,
                    new_detections: 1,
                    skipped: 0,
                    errors: 0,
                    message: 'Working'
                };
            },
            hasOwnerAccess: () => true
        });

        await expect(store.refresh()).resolves.toBeUndefined();

        const running = jobProgressStore.activeJobs.find((job) => job.id === 'backfill:detections:job-healthy');
        expect(running?.current).toBe(3);
        expect(running?.total).toBe(10);
    });
});
