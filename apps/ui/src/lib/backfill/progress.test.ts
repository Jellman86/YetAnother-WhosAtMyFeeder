import { describe, expect, it } from 'vitest';
import {
    describeBackfillProgress,
    formatBackfillProgressSummary,
    resolveRunningBackfillMessage,
    updateScopedBackfillProgress
} from './progress';

describe('updateScopedBackfillProgress', () => {
    it('separates inserted and improved detection counts in progress text', () => {
        expect(formatBackfillProgressSummary(10, 20, 2, 3, 0, 5))
            .toBe('10/20 • 5 new • 2 upd • 3 skip • 0 err');
    });

    it('words progress from its counts, leaving out added visits for weather and saying when the total is unknown', () => {
        const said = (key: string, values: Record<string, number>) => `${key} ${JSON.stringify(values)}`;
        expect(describeBackfillProgress(said, 10, 20, 2, 3, 0, 5)).toBe(
            'jobs.backfill_checked {"processed":10,"total":20} · jobs.backfill_counts_visits {"added":5,"updated":2,"skipped":3,"errors":0}'
        );
        // Weather adds no visits, and an unknown total is said as such instead of a question mark.
        expect(describeBackfillProgress(said, 4, 0, 1, 0, 2)).toBe(
            'jobs.backfill_checked_so_far {"processed":4} · jobs.backfill_counts_weather {"updated":1,"skipped":0,"errors":2}'
        );
    });
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
                '0 of 200 checked'
            )
        ).toBe('Paused while live detections use classifier capacity');
    });
});
