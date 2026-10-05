import { describe, expect, it } from 'vitest';

import leaderboardSource from './Species.svelte?raw';
import heatmapSource from '../components/ActivityHeatmap.svelte?raw';

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

    it('leaves the listening history link to the Explorer', () => {
        expect(leaderboardSource).not.toContain('data-leaderboard-audio-history-link');
        expect(leaderboardSource).not.toContain("toAppPath('/audio')");
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
        expect(leaderboardSource).toContain("trendMeasured(sourceMode, { seen: previousWindowComplete, heard: audioPreviousWindowComplete })");
        expect(leaderboardSource).toContain('audioPreviousWindowComplete = audioResult.value?.previous_window_complete ?? false');
        expect(leaderboardSource).toContain('!trendAvailable\n            ? null');
        expect(leaderboardSource).toContain('{#if trendAvailable}<th scope="col"');
        expect(leaderboardSource).toContain('data-leaderboard-trend-note');
    });

    it('says what stands behind each species besides the classifier', () => {
        expect(leaderboardSource).toContain("import { evidenceFor, isCorroborated, isUnlikelyHere, trendMeasured, type SpeciesEvidence } from '../leaderboard/evidence'");
        expect(leaderboardSource).toContain("let audioKnown = $derived(birdnetEnabled && audioLoadState === 'ready')");
        expect(leaderboardSource).toContain('data-leaderboard-evidence={evidence}');
        expect(leaderboardSource).toContain('data-leaderboard-corroboration');
    });

    it('ranks a window by visits when the route counts them, and names the unit it shows', () => {
        expect(leaderboardSource).toContain('countsAreVisits = windowCountsAreVisits(response)');
        expect(leaderboardSource).toContain("const count = visits ? (s.window_visit_count ?? 0) : (s.window_count ?? 0)");
        expect(leaderboardSource).toContain('delta: count - prevCount');
        // Total has no visit counts, so it must never be labelled as visits.
        expect(leaderboardSource).toContain('const allSpecies = await fetchSpecies(controller.signal);\n                if (loadGeneration !== leaderboardLoadGeneration || controller.signal.aborted) return;\n                species = mapAllTimeSpecies(allSpecies);\n                countsAreVisits = false;');
    });

    it('draws weather under the detections on its own axis, never as a second y-axis', () => {
        expect(leaderboardSource).toContain('data-leaderboard-weather-panel={panel.key}');
        expect(leaderboardSource).not.toContain("yAxisID: item.name === temperatureName");
        expect(leaderboardSource).not.toContain("position: 'right' as const");
        expect(leaderboardSource).toContain('afterFit: alignValueAxis');
        expect(leaderboardSource).toContain('aria-pressed={showTemperature}');
    });

    it('flags a species nothing but the camera backs and no birder reported nearby, in words', () => {
        expect(leaderboardSource).toContain('isUnlikelyHere(evidenceOf(row), row.reported_nearby)');
        expect(leaderboardSource).toContain('data-leaderboard-unlikely-note');
        expect(leaderboardSource).toContain('data-leaderboard-unlikely-reason');
        // Wash, dot and words together, never a coloured rule on the row's edge.
        expect(leaderboardSource).toContain("bg-gradient-to-r from-amber-50 to-transparent dark:from-amber-500/10");
        expect(leaderboardSource).not.toMatch(/border-l-(2|4)[^"]*amber/);
    });

    it('fits the weekday heatmap to its column instead of scrolling it sideways', () => {
        expect(heatmapSource).toContain('repeat(24, minmax(0, 1fr))');
        expect(leaderboardSource).not.toMatch(/min-w-\[650px\]/);
        expect(leaderboardSource).not.toContain('h-[260px] overflow-x-auto');
        // A display:none label leaves the grid and shifts every cell after it by one column.
        expect(heatmapSource).not.toContain('hidden sm:block');
    });

    it('reads a heatmap slot on hover, tap and arrow keys, not through a delayed native title', () => {
        expect(leaderboardSource).toContain('<ActivityHeatmap');
        expect(heatmapSource).not.toContain('title=');
        expect(heatmapSource).toContain('data-heatmap-tooltip');
        expect(heatmapSource).toContain("if (event.pointerType === 'touch') return;");
        expect(heatmapSource).toContain('role="grid"');
        expect(heatmapSource).toContain('aria-activedescendant=');
        expect(heatmapSource).toContain('role="gridcell"');
        expect(heatmapSource).toContain("event.key === 'Escape'");
    });

    it('can show one species\' weekly pattern, and never labels data it is not showing', () => {
        expect(leaderboardSource).toContain('data-leaderboard-heatmap-species');
        expect(leaderboardSource).toContain('fetchDetectionsActivityHeatmapSpan(requestedSpan, controller.signal, requested)');
        expect(leaderboardSource).toContain('let shownHeatmap = $derived(heatmapSpecies ? speciesHeatmap : activityHeatmap)');
        expect(leaderboardSource).toContain('shownHeatmap?.species');
    });

    it('gives a species the same colour in the timeline and the composition chart', () => {
        expect(leaderboardSource).toContain('speciesSeriesColor(speciesSlot().get(entry.species) ?? idx, isDark())');
        expect(leaderboardSource).toContain('backgroundColor: labels.map((_, index) => donutColor(index))');
        expect(leaderboardSource).toContain('data-leaderboard-timeline-legend');
    });
});
