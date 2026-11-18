import { describe, expect, it } from 'vitest';
import { statusStateKey } from './status-words';

describe('the words of a status chip', () => {
    it('says a missing model and a finder to download in their own words, as the Models line does', () => {
        expect(statusStateKey('classifier', { state: 'error', cause: 'model_missing' })).toBe('settings.status.cause.classifier.model_missing');
        expect(statusStateKey('finder', { state: 'degraded', cause: 'not_downloaded' })).toBe('settings.status.cause.finder.not_downloaded');
    });

    it('says the state for every other cause, and "not measured" for no reading', () => {
        expect(statusStateKey('classifier', { state: 'error', cause: 'runtime_failed' })).toBe('settings.status.state.error');
        expect(statusStateKey('finder', { state: 'degraded', cause: 'cpu_fallback' })).toBe('settings.status.state.degraded');
        expect(statusStateKey('mqtt', null)).toBe('settings.status.state.unknown');
    });
});
