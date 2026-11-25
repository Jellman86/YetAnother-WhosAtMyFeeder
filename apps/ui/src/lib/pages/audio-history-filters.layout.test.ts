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
        expect(audioHistorySource).toContain('onchange={(next) => chooseWindow(next)}');
        expect(audioHistorySource).toContain('applied = { ...DEFAULT_AUDIO_HISTORY_FILTERS, window: applied.window };');
    });

    it('go back to the first page and drop the selection when another window is chosen', () => {
        const chooseWindow = audioHistorySource.slice(audioHistorySource.indexOf('function chooseWindow('));
        const body = chooseWindow.slice(0, chooseWindow.indexOf('\n    }\n'));
        expect(body).toContain('if (!isAudioHistoryWindow(next) || next === applied.window) return;');
        expect(body).toContain('offset = 0;');
        expect(body).toContain('selectedIds = [];');
    });

    it('name the periods as the other pages do, with Today first', () => {
        for (const [key, label] of [
            ['today', 'Today'],
            ['24h', 'Last 24 hours'],
            ['7d', 'Last 7 days'],
            ['30d', 'Last 30 days'],
            ['90d', 'Last 90 days'],
            ['1y', 'Last 365 days']
        ]) {
            expect(audioHistorySource).toContain(`$_('audio.filter.${key}', { default: '${label}' })`);
        }
    });

    it('read every figure from one request per load, and read Today again after midnight', () => {
        expect(audioHistorySource).toContain('resolveRequest: () => audioHistoryRequest(');
        expect(audioHistorySource).toContain('fetchHistory: (request) => fetchAudioHistory(request.list)');
        expect(audioHistorySource).toContain('fetchSummary: (request) => fetchAudioSummary(request.aggregate)');
        expect(audioHistorySource).toContain('fetchHeatmap: (request) => fetchAudioActivityHeatmap(request.aggregate)');
        expect(audioHistorySource).toContain('const reading = audioHeatmapReading(request.aggregate);');
        expect(audioHistorySource).toContain('msUntilNextLocalMidnight(new Date()) + 1000');
    });

    it('say plainly that nothing has been heard yet today, and when a guest sees less of the day', () => {
        expect(audioHistorySource).toContain("default: 'No calls heard yet today. Select Refresh to check for new calls.'");
        // The page does not follow live calls, so it never promises they appear on their own.
        expect(audioHistorySource).not.toContain('Calls appear here as BirdNET-Go hears them');
        // A guest whose shared day starts after their midnight is told where it starts, not "today".
        expect(audioHistorySource).toContain("default: 'No calls heard since {time}, when the shared history starts. Select Refresh to check for new calls.'");
    });

    it('show the counted dates only beside a reading of the window named', () => {
        expect(audioHistorySource).toContain("if (!measured || !summary?.window_start || !summary.window_end) return '';");
        expect(audioHistorySource).toContain('data-audio-window-narrowed');
        expect(audioHistorySource).toContain("default: 'Shared history starts at {time}, so calls heard earlier today are not shown.'");
    });

    it('say when the form differs from the list on show', () => {
        expect(audioHistorySource).toContain("$_('audio.filter.changed', { default: 'Filters changed. Apply to update the list.' })");
        expect(audioHistorySource).toContain('window: applied.window');
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
