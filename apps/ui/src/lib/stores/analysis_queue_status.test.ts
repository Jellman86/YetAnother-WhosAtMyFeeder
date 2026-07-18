import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnalysisStatus } from '../api/maintenance';
import { AnalysisQueueStatusStore } from './analysis_queue_status.svelte';
import { jobProgressStore } from './job_progress.svelte';
import { notificationCenter } from './notification_center.svelte';

describe('AnalysisQueueStatusStore', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        jobProgressStore.clearAll();
        notificationCenter.clear();
    });

    afterEach(() => {
        vi.useRealTimers();
        jobProgressStore.clearAll();
        notificationCenter.clear();
    });

    it('ingests status supplied by the single application poller', async () => {
        const status: AnalysisStatus = {
            pending: 12,
            active: 2,
            circuit_open: false,
            pending_capacity: 200,
            pending_available: 188,
            max_concurrent_configured: 4,
            max_concurrent_effective: 2,
            throttled_for_live_pressure: true,
            live_in_flight: 1,
            live_queued: 3
        };
        const store = new AnalysisQueueStatusStore();

        store.ingest(status);

        expect(store.analysisStatus?.pending).toBe(12);
        expect(store.queueByKind.reclassify?.maxConcurrentConfigured).toBe(4);
        expect(store.queueByKind.reclassify?.throttledForLivePressure).toBe(true);
        expect(store.queueByKind.reclassify?.liveInFlight).toBe(1);
        expect(store.queueByKind.reclassify?.liveQueued).toBe(3);
    });

    it('settles a stale synthetic batch job when fresh queue status is empty', async () => {
        jobProgressStore.upsertRunning({
            id: 'reclassify:progress',
            kind: 'reclassify_batch',
            title: 'Batch Analysis',
            current: 0,
            total: 21,
            source: 'poll'
        });
        await vi.advanceTimersByTimeAsync(1001);
        jobProgressStore.markStale(0);
        notificationCenter.upsert({
            id: 'reclassify:progress',
            type: 'process',
            title: 'Batch Analysis',
            message: 'Pending: 21 • Active: 0',
            timestamp: Date.now(),
            read: false,
            meta: {
                route: '/settings/data',
                kind: 'reclassify_batch',
                current: 0,
                total: 21
            }
        });

        const store = new AnalysisQueueStatusStore();
        store.ingest({
            pending: 0,
            active: 0,
            circuit_open: false
        });

        expect(jobProgressStore.activeJobs.find((job) => job.id === 'reclassify:progress')).toBeUndefined();
        const completed = jobProgressStore.historyJobs.find((job) => job.id === 'reclassify:progress');
        expect(completed?.status).toBe('completed');
        expect(completed?.current).toBe(21);
        expect(completed?.total).toBe(21);
        const notification = notificationCenter.items.find((item) => item.id === 'reclassify:progress');
        expect(notification?.type).toBe('update');
        expect(notification?.read).toBe(true);
        expect(notification?.meta?.current).toBe(21);
        expect(notification?.meta?.total).toBe(21);
    });
});
