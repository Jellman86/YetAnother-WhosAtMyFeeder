import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';
import { jobProgressStore } from './job_progress.svelte';

describe('jobProgressStore', () => {
    beforeEach(() => {
        jobProgressStore.clearAll();
        vi.useRealTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('preserves existing counts when running update omits current/total', () => {
        jobProgressStore.upsertRunning({
            id: 'backfill:detections:job-1',
            kind: 'backfill',
            title: 'Backfill',
            current: 12,
            total: 42,
            timestamp: 1000
        });

        jobProgressStore.upsertRunning({
            id: 'backfill:detections:job-1',
            kind: 'backfill',
            title: 'Backfill',
            message: 'still running',
            timestamp: 2000
        });

        const item = jobProgressStore.activeJobs[0];
        expect(item.current).toBe(12);
        expect(item.total).toBe(42);
        expect(item.message).toBe('still running');
    });

    it('keeps progress monotonic and ensures total never drops below current', () => {
        jobProgressStore.upsertRunning({
            id: 'backfill:detections:job-2',
            kind: 'backfill',
            title: 'Backfill',
            current: 30,
            total: 50,
            timestamp: 1000
        });

        // Defensive case: stale/partial backend payload reports lower counters.
        jobProgressStore.upsertRunning({
            id: 'backfill:detections:job-2',
            kind: 'backfill',
            title: 'Backfill',
            current: 5,
            total: 10,
            timestamp: 2000
        });

        const item = jobProgressStore.activeJobs[0];
        expect(item.current).toBe(30);
        expect(item.total).toBe(30);
    });

    it('keeps running totals unknown until the backend reports a denominator', () => {
        jobProgressStore.upsertRunning({
            id: 'backfill:detections:job-unknown',
            kind: 'backfill',
            title: 'Backfill',
            current: 12,
            total: 0,
            timestamp: 1000
        });

        const item = jobProgressStore.activeJobs[0];
        expect(item.current).toBe(12);
        expect(item.total).toBe(0);
        expect(item.etaSeconds).toBeUndefined();
    });

    it('marks only sufficiently idle running jobs as stale', () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-03-05T00:00:00.000Z'));
        const now = Date.now();

        jobProgressStore.upsertRunning({
            id: 'backfill:detections:old',
            kind: 'backfill',
            title: 'Old job',
            current: 1,
            total: 10,
            timestamp: now - 120_000
        });
        jobProgressStore.upsertRunning({
            id: 'backfill:detections:fresh',
            kind: 'backfill',
            title: 'Fresh job',
            current: 1,
            total: 10,
            timestamp: now - 5_000
        });

        jobProgressStore.markStale(60_000);
        const byId = new Map(jobProgressStore.activeJobs.map((item) => [item.id, item]));

        expect(byId.get('backfill:detections:old')?.status).toBe('stale');
        expect(byId.get('backfill:detections:fresh')?.status).toBe('running');
    });

    it('applies per-kind stale threshold overrides so long-running jobs are not prematurely flagged', () => {
        // Regression for issue #33: reclassify_batch and backfill jobs can
        // legitimately go > 5 minutes between SSE updates. The generic 5-min
        // idle threshold was demoting them to 'stale' even while the backend
        // was still actively processing.
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-03-05T00:00:00.000Z'));
        const now = Date.now();

        jobProgressStore.upsertRunning({
            id: 'backfill:detections:long',
            kind: 'backfill',
            title: 'Long backfill',
            current: 10,
            total: 1000,
            timestamp: now - 10 * 60_000 // idle 10 min
        });
        jobProgressStore.upsertRunning({
            id: 'reclassify:batch:long',
            kind: 'reclassify_batch',
            title: 'Reclassify',
            current: 5,
            total: 500,
            timestamp: now - 10 * 60_000
        });
        jobProgressStore.upsertRunning({
            id: 'other:generic:idle',
            kind: 'generic',
            title: 'Generic',
            current: 1,
            total: 10,
            timestamp: now - 6 * 60_000 // idle 6 min, over the 5-min generic threshold
        });

        jobProgressStore.markStale(5 * 60_000, {
            backfill: 30 * 60_000,
            reclassify_batch: 30 * 60_000
        });

        const byId = new Map(jobProgressStore.activeJobs.map((item) => [item.id, item]));
        expect(byId.get('backfill:detections:long')?.status).toBe('running');
        expect(byId.get('reclassify:batch:long')?.status).toBe('running');
        expect(byId.get('other:generic:idle')?.status).toBe('stale');
    });

    it('closeActiveByPrefix is idempotent when status already matches', () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-03-05T00:00:00.000Z'));

        jobProgressStore.upsertRunning({
            id: 'backfill:detections:job-3',
            kind: 'backfill',
            title: 'Backfill',
            current: 3,
            total: 20,
            timestamp: Date.now() - 10_000
        });

        vi.setSystemTime(new Date('2026-03-05T00:00:05.000Z'));
        jobProgressStore.closeActiveByPrefix('backfill:detections:', 'stale');
        const first = jobProgressStore.activeJobs.find((item) => item.id === 'backfill:detections:job-3');
        expect(first?.status).toBe('stale');
        const firstUpdatedAt = first?.updatedAt;

        vi.setSystemTime(new Date('2026-03-05T00:00:10.000Z'));
        jobProgressStore.closeActiveByPrefix('backfill:detections:', 'stale');
        const second = jobProgressStore.activeJobs.find((item) => item.id === 'backfill:detections:job-3');
        expect(second?.status).toBe('stale');
        expect(second?.updatedAt).toBe(firstUpdatedAt);
    });

    it('does not revive a completed job when a stale running update arrives', () => {
        // Regression for issue #33: a backfill_progress SSE that arrives after
        // backfill_complete must not demote the terminal job back to 'running'.
        jobProgressStore.upsertRunning({
            id: 'backfill:detections:job-revival',
            kind: 'backfill',
            title: 'Backfill',
            current: 8,
            total: 10,
            timestamp: 1000
        });

        jobProgressStore.markCompleted({
            id: 'backfill:detections:job-revival',
            kind: 'backfill',
            title: 'Backfill done',
            current: 10,
            total: 10,
            timestamp: 2000
        });

        // Stale progress event arrives after completion
        jobProgressStore.upsertRunning({
            id: 'backfill:detections:job-revival',
            kind: 'backfill',
            title: 'Backfill',
            current: 9,
            total: 10,
            timestamp: 3000
        });

        expect(jobProgressStore.activeJobs.find((e) => e.id === 'backfill:detections:job-revival')).toBeUndefined();
        const historyItem = jobProgressStore.historyJobs.find((e) => e.id === 'backfill:detections:job-revival');
        expect(historyItem?.status).toBe('completed');
        expect(historyItem?.current).toBe(10);
        expect(historyItem?.total).toBe(10);
    });

    it('does not revive a failed job when a stale running update arrives', () => {
        jobProgressStore.markFailed({
            id: 'backfill:detections:job-failed',
            kind: 'backfill',
            title: 'Backfill failed',
            current: 2,
            total: 10,
            timestamp: 1000
        });

        jobProgressStore.upsertRunning({
            id: 'backfill:detections:job-failed',
            kind: 'backfill',
            title: 'Backfill',
            current: 3,
            total: 10,
            timestamp: 2000
        });

        expect(jobProgressStore.activeJobs.find((e) => e.id === 'backfill:detections:job-failed')).toBeUndefined();
        expect(jobProgressStore.historyJobs.find((e) => e.id === 'backfill:detections:job-failed')?.status).toBe('failed');
    });

    it('markCompleted can still finalize a running job (terminal guard only blocks revival)', () => {
        jobProgressStore.upsertRunning({
            id: 'backfill:detections:job-finalize',
            kind: 'backfill',
            title: 'Backfill',
            current: 5,
            total: 10,
            timestamp: 1000
        });

        jobProgressStore.markCompleted({
            id: 'backfill:detections:job-finalize',
            kind: 'backfill',
            title: 'Backfill',
            current: 10,
            total: 10,
            timestamp: 2000
        });

        expect(jobProgressStore.historyJobs.find((e) => e.id === 'backfill:detections:job-finalize')?.status).toBe('completed');
    });

    it('forces completed current to be at least total', () => {
        jobProgressStore.upsertRunning({
            id: 'backfill:detections:job-4',
            kind: 'backfill',
            title: 'Backfill',
            current: 8,
            total: 10,
            timestamp: 1000
        });

        jobProgressStore.markCompleted({
            id: 'backfill:detections:job-4',
            kind: 'backfill',
            title: 'Backfill done',
            current: 9,
            total: 10,
            timestamp: 2000
        });

        const item = jobProgressStore.historyJobs.find((entry) => entry.id === 'backfill:detections:job-4');
        expect(item?.status).toBe('completed');
        expect(item?.current).toBe(10);
        expect(item?.total).toBe(10);
    });
});
