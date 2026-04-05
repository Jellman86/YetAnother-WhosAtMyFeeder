import { describe, expect, it } from 'vitest';
import {
    resolveRunningBackfillMessage,
    updateScopedBackfillProgress
} from './progress';

describe('updateScopedBackfillProgress', () => {
    it('does not carry an older total into a new running job before the backend reports one', () => {
        const next = updateScopedBackfillProgress(
            { jobId: 'job-old', total: 200 },
            {
                id: 'job-new',
                status: 'running',
                processed: 0,
                total: 0
            }
        );

        expect(next).toEqual({
            jobId: 'job-new',
            total: 0
        });
    });

    it('preserves the known total for the same running job when a later payload omits it', () => {
        const next = updateScopedBackfillProgress(
            { jobId: 'job-1', total: 200 },
            {
                id: 'job-1',
                status: 'running',
                processed: 0,
                total: 0
            }
        );

        expect(next).toEqual({
            jobId: 'job-1',
            total: 200
        });
    });

    it('uses observed progress as a scoped total when a running job never reports one', () => {
        const next = updateScopedBackfillProgress(
            { jobId: 'job-1', total: 0 },
            {
                id: 'job-1',
                status: 'running',
                processed: 17,
                total: 0
            }
        );

        expect(next).toEqual({
            jobId: 'job-1',
            total: 17
        });
    });

    it('prefers an explicit running status message over a generated summary', () => {
        expect(
            resolveRunningBackfillMessage(
                {
                    status: 'running',
                    message: 'Paused while live detections use classifier capacity'
                },
                '0/200 • 0 upd • 0 skip • 0 err'
            )
        ).toBe('Paused while live detections use classifier capacity');
    });
});
