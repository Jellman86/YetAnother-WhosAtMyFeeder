import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnalysisStatus } from '../api/maintenance';
import { AnalysisQueueStatusStore } from './analysis_queue_status.svelte';

describe('AnalysisQueueStatusStore', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('shares a single poller across multiple retainers and stops when released', async () => {
        const fetchAnalysisStatus = vi.fn(async (): Promise<AnalysisStatus> => ({
            pending: 12,
            active: 2,
            circuit_open: false,
            pending_capacity: 200,
            pending_available: 188,
            max_concurrent_configured: 4,
            max_concurrent_effective: 2
        }));
        const recordError = vi.fn();
        const store = new AnalysisQueueStatusStore({
            fetchAnalysisStatus,
            pollIntervalMs: 5000,
            hasOwnerAccess: () => true,
            recordError
        });

        const releaseOne = store.retain();
        const releaseTwo = store.retain();
        await Promise.resolve();

        expect(fetchAnalysisStatus).toHaveBeenCalledTimes(1);
        expect(store.analysisStatus?.pending).toBe(12);
        expect(store.queueByKind.reclassify?.maxConcurrentConfigured).toBe(4);

        await vi.advanceTimersByTimeAsync(5000);
        expect(fetchAnalysisStatus).toHaveBeenCalledTimes(2);

        releaseOne();
        await vi.advanceTimersByTimeAsync(5000);
        expect(fetchAnalysisStatus).toHaveBeenCalledTimes(3);

        releaseTwo();
        await vi.advanceTimersByTimeAsync(5000);
        expect(fetchAnalysisStatus).toHaveBeenCalledTimes(3);
        expect(recordError).not.toHaveBeenCalled();
    });
});
