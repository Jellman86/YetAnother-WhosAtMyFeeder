import { describe, expect, it } from 'vitest';
import {
    DEFAULT_AUDIO_HISTORY_FILTERS,
    audioHistoryFiltersDiffer,
    settledAudioHistoryFilters
} from './audio-history-filters';

describe('audio history filters', () => {
    it('reports no change for the form as applied', () => {
        expect(audioHistoryFiltersDiffer({ ...DEFAULT_AUDIO_HISTORY_FILTERS }, DEFAULT_AUDIO_HISTORY_FILTERS)).toBe(false);
    });

    it('reports a change to any filter the list depends on', () => {
        for (const change of [{ days: 7 }, { species: 'Dunnock' }, { source: 'BirdCam' }, { minConfidence: 0.5 }]) {
            expect(audioHistoryFiltersDiffer({ ...DEFAULT_AUDIO_HISTORY_FILTERS, ...change }, DEFAULT_AUDIO_HISTORY_FILTERS)).toBe(true);
        }
    });

    it('ignores whitespace the request would trim', () => {
        const applied = { ...DEFAULT_AUDIO_HISTORY_FILTERS, species: 'Dunnock' };
        expect(audioHistoryFiltersDiffer({ ...applied, species: '  Dunnock ' }, applied)).toBe(false);
    });

    it('settles text and numbers as the request sends them', () => {
        expect(settledAudioHistoryFilters({ days: 7, species: ' Robin ', source: ' mic ', minConfidence: 0.25 })).toEqual({
            days: 7,
            species: 'Robin',
            source: 'mic',
            minConfidence: 0.25
        });
    });
});
