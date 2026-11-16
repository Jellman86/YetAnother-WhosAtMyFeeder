import { describe, expect, it } from 'vitest';
import { diagnosticWordsKey } from './diagnostic-words';

describe('diagnosticWordsKey', () => {
    it('words a known backend reason code instead of showing its raw message', () => {
        expect(diagnosticWordsKey('drop_classify_snapshot_timeout')).toBe('classify_snapshot_timeout');
        expect(diagnosticWordsKey('drop_classify_snapshot_overloaded')).toBe('classify_snapshot_overloaded');
        expect(diagnosticWordsKey('drop_save_and_notify_failed')).toBe('save_and_notify_failed');
        expect(diagnosticWordsKey('stale_job')).toBe('stale_job');
        expect(diagnosticWordsKey(' DROP_CLASSIFIER_EMPTY_RESULTS ')).toBe('classifier_empty_results');
    });

    it('words a failed or timed-out pipeline stage, whose message carries the raw exception', () => {
        // "Stage classify failed: {exception}" can hold paths and URLs; the page never leads with it.
        expect(diagnosticWordsKey('stage_failure')).toBe('stage_failure');
        expect(diagnosticWordsKey('stage_timeout')).toBe('stage_timeout');
    });

    it('gives any other code a generic cause, never the raw message as its title', () => {
        expect(diagnosticWordsKey('drop_something_new')).toBe('generic');
        expect(diagnosticWordsKey('refresh_failed')).toBe('generic');
        expect(diagnosticWordsKey('')).toBe('generic');
        expect(diagnosticWordsKey(null)).toBe('generic');
    });
});
