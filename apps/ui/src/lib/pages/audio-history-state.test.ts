import { describe, expect, it } from 'vitest';
import { audioReading } from './audio-history-state';

describe('audioReading', () => {
    it('is loading until an answer arrives, so nothing shows a zero that was not measured', () => {
        expect(audioReading({ loading: true, error: null, stale: false, total: null })).toBe('loading');
        expect(audioReading({ loading: false, error: null, stale: false, total: null })).toBe('loading');
    });

    it('is failed when the read failed and nothing from it is on screen', () => {
        expect(audioReading({ loading: false, error: 'boom', stale: false, total: null })).toBe('failed');
    });

    it('is stale when a refresh failed but the earlier reading for the same request is kept', () => {
        expect(audioReading({ loading: false, error: 'boom', stale: true, total: 12 })).toBe('stale');
    });

    it('is empty only when the window was measured and held nothing', () => {
        expect(audioReading({ loading: false, error: null, stale: false, total: 0 })).toBe('empty');
        expect(audioReading({ loading: false, error: null, stale: false, total: 3 })).toBe('ready');
    });
});
