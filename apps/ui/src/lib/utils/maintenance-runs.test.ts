import { describe, expect, it } from 'vitest';
import type { MaintenanceLastRun } from '../api/maintenance';
import { lastRunSentence, timezoneRepairBlockedReason } from './maintenance-runs';

const translate = (key: string, options?: { default?: string; values?: Record<string, string | number> }): string => {
    let text = options?.default ?? key;
    for (const [name, value] of Object.entries(options?.values ?? {})) text = text.replaceAll(`{${name}}`, String(value));
    return text;
};
const formatWhen = (): string => '15/11/2026 09:30';

function run(overrides: Partial<MaintenanceLastRun>): MaintenanceLastRun {
    return { kind: 'taxonomy', status: 'completed', finished_at: '2026-11-15T09:30:00Z', checked: 120, changed: 7, ...overrides } as MaintenanceLastRun;
}

describe('lastRunSentence', () => {
    it('says plainly when a job has never been recorded', () => {
        expect(lastRunSentence(null, 'taxonomy', { translate, formatWhen })).toBe('No run recorded yet.');
    });

    it('says what a taxonomy repair checked and changed', () => {
        expect(lastRunSentence(run({}), 'taxonomy', { translate, formatWhen })).toBe('Last run 15/11/2026 09:30: 7 of 120 names repaired.');
    });

    it('says what a timezone scan found', () => {
        expect(lastRunSentence(run({ kind: 'timezone_scan', checked: 40, changed: 0 }), 'timezone_scan', { translate, formatWhen })).toBe(
            'Last scan 15/11/2026 09:30: none of 40 detections need a repair.'
        );
    });

    it('says how many unknown visits were queued', () => {
        expect(lastRunSentence(run({ kind: 'analyze_unknowns', changed: 3 }), 'analyze_unknowns', { translate, formatWhen })).toBe(
            'Last run 15/11/2026 09:30: 3 visits queued for video analysis.'
        );
    });

    it('says a run that did not finish did not finish, without inventing counts', () => {
        expect(lastRunSentence(run({ status: 'failed', checked: null, changed: null }), 'taxonomy', { translate, formatWhen })).toBe(
            'The last run, 15/11/2026 09:30, did not finish.'
        );
    });
});

describe('timezoneRepairBlockedReason', () => {
    it('asks for a scan before a repair can run', () => {
        expect(timezoneRepairBlockedReason(null)).toBe('scan_first');
    });

    it('says there is nothing to repair after a scan that found nothing', () => {
        expect(timezoneRepairBlockedReason({ summary: { repair_candidate_count: 0 } })).toBe('nothing_to_repair');
    });

    it('says the last recorded scan found nothing, instead of asking for a scan', () => {
        expect(timezoneRepairBlockedReason(null, run({ kind: 'timezone_scan', checked: 500, changed: 0 }))).toBe('nothing_last_scan');
    });

    it('still asks for a scan when the last recorded one found work or did not finish', () => {
        expect(timezoneRepairBlockedReason(null, run({ kind: 'timezone_scan', changed: 3 }))).toBe('scan_first');
        expect(timezoneRepairBlockedReason(null, run({ kind: 'timezone_scan', status: 'failed', changed: null }))).toBe('scan_first');
    });

    it('allows the repair once a scan found something', () => {
        expect(timezoneRepairBlockedReason({ summary: { repair_candidate_count: 2 } })).toBeNull();
    });
});
