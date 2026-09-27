import { describe, expect, it } from 'vitest';

import leaderboardSource from './Species.svelte?raw';

describe('leaderboard field-journal layout', () => {
    it('names the sunrise and sunset windows instead of showing bare times', () => {
        expect(leaderboardSource).toContain("{$_('leaderboard.sunrise')} {timeline.sunrise_range}");
        expect(leaderboardSource).toContain("{$_('leaderboard.sunset')} {timeline.sunset_range}");
    });

    it('shows average confidence as a percentage like every other confidence', () => {
        expect(leaderboardSource).toContain(
            "{item.avg_confidence != null ? `${Math.round(item.avg_confidence * 100)}%` : '—'}"
        );
        expect(leaderboardSource).not.toContain('avg_confidence ?? 0).toFixed(2)');
    });

    it('puts the working ranking surface before secondary analytics', () => {
        const rankings = leaderboardSource.indexOf('data-leaderboard-rankings');
        const analytics = leaderboardSource.indexOf('data-leaderboard-analytics');

        expect(rankings).toBeGreaterThan(-1);
        expect(analytics).toBeGreaterThan(rankings);
    });

    it('uses dedicated mobile and desktop ranking presentations', () => {
        expect(leaderboardSource).toContain('data-leaderboard-mobile-rankings');
        expect(leaderboardSource).toContain('data-leaderboard-desktop-rankings');
        expect(leaderboardSource).not.toContain('min-w-[900px]');
        expect(leaderboardSource).not.toContain('role="button"');
    });

    it('sorts explicitly by the selected source and deduplicates audio-only rows', () => {
        expect(leaderboardSource).toContain('function leaderboardTableRows(mode: SourceMode)');
        expect(leaderboardSource).toContain("mode === 'heard'");
        expect(leaderboardSource).toContain("mode === 'both'");
        expect(leaderboardSource).toContain('if (sciKey) usedAudioKeys.add(sciKey)');
        expect(leaderboardSource).toContain('if (nmKey) usedAudioKeys.add(nmKey)');
    });

    it('removes the tiny-label, emoji-medal, and card-wall treatments', () => {
        expect(leaderboardSource).not.toMatch(/text-\[(?:9|10|11)px\]/);
        expect(leaderboardSource.match(/card-base/g) ?? []).toHaveLength(0);
        expect(leaderboardSource).not.toMatch(/[🐦🥇🥈🥉]/u);
        expect(leaderboardSource).not.toContain('topSpecies');
    });

    it('uses accessible section icons and touch-sized controls', () => {
        expect(leaderboardSource.match(/data-leaderboard-section-icon/g) ?? []).toHaveLength(2);
        expect(leaderboardSource.match(/data-leaderboard-section-icon[^>]+aria-hidden="true"/g) ?? []).toHaveLength(2);
        expect(leaderboardSource).toContain('min-h-11');
        expect(leaderboardSource).toContain('focus-visible:ring-2 focus-visible:ring-brand-500');
    });

    it('uses round species portraits throughout the ranking surface', () => {
        expect(leaderboardSource.match(/data-leaderboard-species-portrait/g) ?? []).toHaveLength(2);
        expect(leaderboardSource.match(/data-leaderboard-species-portrait[^>]+rounded-full/g) ?? []).toHaveLength(2);
    });

    it('exposes toggle state and table headings to assistive technology', () => {
        expect(leaderboardSource).toContain("aria-pressed={span === 'month'}");
        expect(leaderboardSource).toContain("aria-pressed={sourceMode === 'seen'}");
        expect(leaderboardSource.match(/scope="col"/g)?.length ?? 0).toBeGreaterThanOrEqual(6);
        expect(leaderboardSource).toContain('tabular-nums');
    });

    it('links BirdNET-enabled leaderboards to the complete listening history', () => {
        expect(leaderboardSource).toContain("import { toAppPath } from '../app/url-base'");
        expect(leaderboardSource).toContain('data-leaderboard-audio-history-link');
        expect(leaderboardSource).toContain("href={toAppPath('/audio')}");
        expect(leaderboardSource).toContain("$_('nav.audio_history')");
    });

    it('does not turn an unavailable BirdNET result into measured zero activity', () => {
        expect(leaderboardSource).toContain("type AudioLoadState = 'disabled' | 'loading' | 'ready' | 'error'");
        expect(leaderboardSource).toContain("audioLoadState = 'error'");
        expect(leaderboardSource).toContain("sourceMode !== 'seen' && audioLoadState === 'error'");
        expect(leaderboardSource).toContain('leaderboard.audio_unavailable_title');
        expect(leaderboardSource).toContain('let leaderboardRows = $derived(leaderboardTableRows(sourceMode))');
    });

    it('uses source-aware comparisons in both ranking layouts', () => {
        expect(leaderboardSource).toContain('heard_prev_count: heard?.heard_prev_count ?? null');
        expect(leaderboardSource).toContain('trendForMode(item, sourceMode)');
        expect(leaderboardSource).toContain('deltaForMode(row, sourceMode)');
        expect(leaderboardSource).toContain('activityTimestampForMode(item, sourceMode)');
    });

    it('states the window in one standing band, with rising only when a trend was measured', () => {
        expect(leaderboardSource).toContain('data-leaderboard-standing');
        expect(leaderboardSource).toContain("let trendAvailable = $derived(span !== 'all' && previousWindowComplete)");
        expect(leaderboardSource).toContain('!trendAvailable\n            ? null');
        expect(leaderboardSource).toContain('{#if trendAvailable}<th scope="col"');
        expect(leaderboardSource).toContain('data-leaderboard-trend-note');
    });

    it('says what stands behind each species besides the classifier', () => {
        expect(leaderboardSource).toContain("import { evidenceFor, isCorroborated, type SpeciesEvidence } from '../leaderboard/evidence'");
        expect(leaderboardSource).toContain("let audioKnown = $derived(birdnetEnabled && audioLoadState === 'ready')");
        expect(leaderboardSource).toContain('data-leaderboard-evidence={evidence}');
        expect(leaderboardSource).toContain('data-leaderboard-corroboration');
    });

    it('fits the weekday heatmap to its column instead of scrolling it sideways', () => {
        const heatmap = leaderboardSource.slice(leaderboardSource.indexOf('data-leaderboard-heatmap-grid') - 200);
        expect(heatmap).toContain('repeat(24, minmax(0, 1fr))');
        expect(leaderboardSource).not.toMatch(/min-w-\[650px\]/);
        expect(leaderboardSource).not.toContain('h-[260px] overflow-x-auto');
        // Cells are read through the hidden table; 168 inert buttons were 168 Tab stops.
        expect(heatmap.slice(0, 2500)).not.toContain('<button');
        // sr-only cannot shrink a table itself; unwrapped, it widened the whole page to 1994px.
        expect(leaderboardSource).toContain('<div class="sr-only"><table>');
        // A display:none label leaves the grid and shifts every cell after it by one column.
        expect(heatmap.slice(0, 2500)).not.toContain('hidden sm:block');
    });

    it('gives a species the same colour in the timeline and the composition chart', () => {
        expect(leaderboardSource).toContain('speciesSeriesColor(speciesSlot().get(entry.species) ?? idx, isDark())');
        expect(leaderboardSource).toContain('backgroundColor: labels.map((_, index) => donutColor(index))');
        expect(leaderboardSource).toContain('data-leaderboard-timeline-legend');
    });
});
