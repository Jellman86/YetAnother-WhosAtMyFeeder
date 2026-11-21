import { describe, expect, it } from 'vitest';
import {
    backfillOutcomeNote,
    withOutcomeNote,
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
    it('never reads a finished job as still counting', () => {
        const said = (key: string, values: Record<string, number>) => `${key} ${JSON.stringify(values)}`;
        // An empty range checked nothing: it says so, not "0 checked so far".
        expect(describeBackfillProgress(said, 0, 0, 0, 0, 0, 0, true)).toBe('jobs.backfill_nothing_to_check {}');
        // A finished job that never reported a total checked what it processed.
        expect(describeBackfillProgress(said, 7, 0, 1, 6, 0, undefined, true)).toBe(
            'jobs.backfill_checked {"processed":7,"total":7} · jobs.backfill_counts_weather {"updated":1,"skipped":6,"errors":0}'
        );
        // A running job with no total yet is still counting.
        expect(describeBackfillProgress(said, 0, 0, 0, 0, 0, 0)).toContain('jobs.backfill_checked_so_far');
    });

    it('keeps the reason a finished job gives beyond its counts', () => {
        expect(backfillOutcomeNote('Weather archive unavailable for range')).toEqual({ kind: 'known', key: 'jobs.backfill_reason_weather_unavailable' });
        expect(backfillOutcomeNote('No detections found in range.')).toEqual({ kind: 'known', key: 'jobs.backfill_reason_nothing_in_range' });
        // Why rows were skipped is something only the server can say, so it is quoted as the server's.
        expect(backfillOutcomeNote('Added 2 new detection(s), 3 already existed, 1 were below the confidence threshold')).toEqual({
            kind: 'quoted', message: 'Added 2 new detection(s), 3 already existed, 1 were below the confidence threshold'
        });
        // A sentence that only repeats the counts adds nothing.
        expect(backfillOutcomeNote('Added 5 new detection(s)')).toBeNull();
        expect(backfillOutcomeNote('No new detections found, 2 existing detection(s) improved, 4 skipped')).toBeNull();
        expect(backfillOutcomeNote('Updated 3 detection(s), 2 skipped')).toBeNull();
        expect(backfillOutcomeNote('  ')).toBeNull();
        expect(backfillOutcomeNote(null)).toBeNull();
    });

    it('puts the reason after the summary, in the app\'s words where it has them', () => {
        const say = (key: string, values?: Record<string, string>) => (values ? `${key} ${JSON.stringify(values)}` : key);
        expect(withOutcomeNote('120 of 120 checked', 'Weather archive unavailable for range', say)).toBe(
            '120 of 120 checked jobs.backfill_reason_weather_unavailable'
        );
        expect(withOutcomeNote('5 of 5 checked', 'Added 1 new detection(s), 4 already existed', say)).toBe(
            '5 of 5 checked jobs.backfill_server_note {"message":"Added 1 new detection(s), 4 already existed"}'
        );
        expect(withOutcomeNote('5 of 5 checked', 'Added 5 new detection(s)', say)).toBe('5 of 5 checked');
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
