import { describe, expect, it, vi } from 'vitest';
import { createReclassifyRecovery } from './reclassify_recovery';

function staleJob(id: string) {
    return {
        id,
        kind: 'reclassify',
        title: 'Reclassify',
        message: 'working',
        route: '/events',
        status: 'stale',
        current: 2,
        total: 8
    };
}

describe('createReclassifyRecovery', () => {
    it('extracts event ids from reclassify job ids', () => {
        const recovery = createReclassifyRecovery({
            fetchStatus: async () => ({
                video_classification_status: null,
                video_classification_error: null
            }),
            jobProgress: {
                activeJobs: [],
                upsertRunning: () => undefined,
                markCompleted: () => undefined,
                markFailed: () => undefined
            },
            logger: { warn: () => undefined },
            now: () => 1
        });

        expect(recovery.parseEventId('reclassify:abc')).toBe('abc');
        expect(recovery.parseEventId('reclassify:   abc-123   ')).toBe('abc-123');
        expect(recovery.parseEventId('backfill:abc')).toBeNull();
    });

    it('marks stale jobs completed when backend reports completed', async () => {
        const markCompleted = vi.fn();
        const recovery = createReclassifyRecovery({
            fetchStatus: async () => ({
                video_classification_status: 'completed',
                video_classification_error: null
            }),
            jobProgress: {
                activeJobs: [staleJob('reclassify:evt-1')],
                upsertRunning: vi.fn(),
                markCompleted,
                markFailed: vi.fn()
            },
            logger: { warn: () => undefined },
            now: () => 100_000
        });

        await recovery.reconcile();
        expect(markCompleted).toHaveBeenCalledTimes(1);
        expect(markCompleted.mock.calls[0][0].id).toBe('reclassify:evt-1');
        expect(markCompleted.mock.calls[0][0].source).toBe('poll');
    });

    it('marks stale jobs failed when backend reports failure', async () => {
        const markFailed = vi.fn();
        const recovery = createReclassifyRecovery({
            fetchStatus: async () => ({
                video_classification_status: 'failed',
                video_classification_error: 'timeout'
            }),
            jobProgress: {
                activeJobs: [staleJob('reclassify:evt-2')],
                upsertRunning: vi.fn(),
                markCompleted: vi.fn(),
                markFailed
            },
            logger: { warn: () => undefined },
            now: () => 100_000
        });

        await recovery.reconcile();
        expect(markFailed).toHaveBeenCalledTimes(1);
        expect(markFailed.mock.calls[0][0].id).toBe('reclassify:evt-2');
        expect(markFailed.mock.calls[0][0].message).toBe('timeout');
    });
});
