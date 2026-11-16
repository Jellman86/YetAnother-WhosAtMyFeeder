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

    it('leaves a code it does not know to the raw message, rather than guessing', () => {
        expect(diagnosticWordsKey('drop_something_new')).toBeNull();
        expect(diagnosticWordsKey('')).toBeNull();
        expect(diagnosticWordsKey(null)).toBeNull();
    });
});
