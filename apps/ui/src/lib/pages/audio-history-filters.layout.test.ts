import { describe, expect, it } from 'vitest';
import audioHistorySource from './AudioHistory.svelte?raw';

describe('audio history filters', () => {
    it('apply as one form, so Enter in any field applies them', () => {
        expect(audioHistorySource).toContain('onsubmit={applyFilters}');
        expect(audioHistorySource).toMatch(/<button type="submit" class="btn btn-primary[^"]*"[^>]*>\{\$_\('common\.apply'/);
    });

    it('apply the window as it is chosen, with the Leaderboard\'s control, and keep it through Clear', () => {
        expect(audioHistorySource).toContain('data-audio-window-bar');
        expect(audioHistorySource).toContain('data-audio-window-select');
        expect(audioHistorySource).toContain('onchange={(next) => chooseWindow(Number(next))}');
        expect(audioHistorySource).toContain('applied = { ...DEFAULT_AUDIO_HISTORY_FILTERS, days: applied.days };');
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

    it('sets every filter label on one line height, so the labels and their fields line up', () => {
        // An inline label takes the paragraph's line height and a flex one takes text-xs's, which set
        // "Min confidence" about 4px above the other two.
        expect(audioHistorySource.match(/<span class="block text-xs font-semibold leading-4 text-muted">/g)).toHaveLength(2);
        expect(audioHistorySource).toContain('<span class="flex justify-between gap-2 text-xs font-semibold leading-4 text-muted">');
        expect(audioHistorySource).toContain('type="range" min="0" max="1" step="0.05" class="block min-h-11');
    });
});
