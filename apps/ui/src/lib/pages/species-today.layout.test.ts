import { describe, expect, it } from 'vitest';
import speciesSource from './Species.svelte?raw';
import modalSource from '../components/SpeciesDetailModal.svelte?raw';
import en from '../i18n/locales/en/leaderboard.json';

describe('the Leaderboard Today period', () => {
    it('offers Today first and keeps the month as the default window', () => {
        expect(speciesSource).toContain("{ value: 'today', label: $_('leaderboard.sort_by_today', { default: 'Today' }) }");
        expect(speciesSource).toContain("let span = $state<LeaderboardSpan>(pageLink.span ?? 'month');");
    });

    it('words every period as the rest of the app does', () => {
        expect(en.sort_by_today).toBe('Today');
        expect(en.sort_by_day).toBe('Last 24 hours');
        expect(en.sort_by_week).toBe('Last 7 days');
        expect(en.sort_by_month).toBe('Last 30 days');
        expect(en.sort_by_total).toBe('All time');
        expect(en.total_sightings).toBe(en.sort_by_total);
    });

    it('names Today in the species dialog opened from a Today row', () => {
        expect(modalSource).toContain("if (openedFrom?.span === 'today') return $_('species_detail.visits_today', { default: 'Visits, today' });");
    });

    it('keeps the heatmap table column a day of the week, not the period', () => {
        expect(speciesSource).toContain("day: $_('leaderboard.heatmap_day_column', { default: 'Day' })");
        expect(speciesSource).not.toContain("day: $_('leaderboard.sort_by_day'");
    });

    it('asks every source and chart for the selected period', () => {
        expect(speciesSource).toContain('fetchLeaderboardSpecies(requestedSpan, controller.signal)');
        expect(speciesSource).toContain('fetchAudioSpeciesLeaderboard(requestedSpan, controller.signal)');
        expect(speciesSource).toContain('fetchDetectionsTimelineSpan(requestedSpan, {');
        expect(speciesSource).toContain('fetchDetectionsActivityHeatmapSpan(requestedSpan, controller.signal)');
        expect(speciesSource).toContain('fetchDetectionsActivityHeatmapSpan(requestedSpan, controller.signal, requested)');
        expect(speciesSource).toContain('fetchLeaderboardPortraits(requestedSpan, controller.signal, RANKING_PORTRAITS)');
    });

    it('drops an answer for a period the reader has already left', () => {
        // Each loader aborts its request when the span changes and ignores what arrives after.
        expect(speciesSource.match(/return \(\) => controller\.abort\(\);/g)?.length ?? 0).toBeGreaterThanOrEqual(3);
        expect(speciesSource).toContain('if (wallFetched.span !== span) return [];');
        expect(speciesSource).toContain('if (loadGeneration !== leaderboardLoadGeneration || controller.signal.aborted) return;');
    });

    it('says an early Today is empty because the day has just begun', () => {
        expect(speciesSource).toMatch(/span === 'today'\}\s*<h2[^>]*>\{\$_\('leaderboard\.today_empty_title'/);
        expect(speciesSource).toMatch(/span === 'today'\s*\? \$_\('leaderboard\.today_empty_desc'/);
        expect(en.today_empty_title).toBe('No visits yet today');
    });

    it('states the start a guest window was cut to', () => {
        expect(speciesSource).toContain('shortenedWindowStart(sourceMode, seenWindowReading, heardWindowReading)');
        expect(speciesSource).toContain('data-leaderboard-window-shortened');
        expect(en.window_shortened_note).toContain('{time}');
    });

    it('withholds the trend with its real reason', () => {
        expect(speciesSource).toContain("trendGap(sourceMode, seenWindowReading, heardWindowReading)");
        expect(speciesSource).toContain("$_('leaderboard.trend_not_comparable_shared'");
        expect(speciesSource).toContain("$_('leaderboard.trend_not_comparable_clock'");
        expect(speciesSource).toMatch(/currentTrendGap === 'history' && trendHistoryStart/);
    });
});
