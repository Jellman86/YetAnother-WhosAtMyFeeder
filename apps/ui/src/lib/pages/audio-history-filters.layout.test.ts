import { describe, expect, it } from 'vitest';
import audioHistorySource from './AudioHistory.svelte?raw';

describe('audio history filters', () => {
    it('apply as one form, so Enter in any field applies them', () => {
        expect(audioHistorySource).toContain('onsubmit={applyFilters}');
        expect(audioHistorySource).toMatch(/<button type="submit" class="btn btn-primary[^"]*"[^>]*>\{\$_\('common\.apply'/);
    });

    it('say when the form differs from the list on show', () => {
        expect(audioHistorySource).toContain("$_('audio.filter.changed', { default: 'Filters changed. Apply to update the list.' })");
        expect(audioHistorySource).toContain('days: applied.days');
    });
});

describe('audio spectrograms', () => {
    it('fall back to the waveform placeholder when one fails to load', () => {
        expect(audioHistorySource.match(/onerror=\{\(\) => markSpectrogramFailed\(detection\.birdnet_id\)\}/g)).toHaveLength(2);
        expect(audioHistorySource).toContain("default: 'Spectrogram of the {species} call'");
        expect(audioHistorySource).not.toContain('alt={detection.species}');
    });
});
