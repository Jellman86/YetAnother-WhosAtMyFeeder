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
        expect(speciesSource).toContain('if (wallFetched.span !== loadedSpan) return [];');
        expect(speciesSource).toContain('const superseded = () => loadGeneration !== leaderboardLoadGeneration || controller.signal.aborted;');
    });

    it('says an early Today is empty only when it answered with nothing at all', () => {
        expect(speciesSource).toContain("!error && !loading && loadedSpan === 'today' && sourceMode !== 'heard' && species.length === 0");
        expect(speciesSource).toMatch(/\{#if todayMeasuredEmpty\}\s*<h2[^>]*>\{\$_\('leaderboard\.today_empty_title'/);
        expect(speciesSource).toMatch(/: todayMeasuredEmpty\s*\? \$_\('leaderboard\.today_empty_desc'/);
        // A failed load shows its alert alone, never an empty board that claims it was measured.
        expect(speciesSource).toMatch(/\{:else if error && leaderboardRows\.length === 0\}\s*<!--[^>]*-->\s*\{:else if leaderboardRows\.length === 0\}/);
        expect(en.today_empty_title).toBe('No visits yet today');
    });

    it('names the rows and charts by the period they were counted over while the next one loads', () => {
        expect(speciesSource).toContain('let shownSpan = $derived(loadedSpan ?? span);');
        expect(speciesSource).toContain("let timelineSpan = $derived<string | undefined>(timeline?.span ?? shownSpan);");
        expect(speciesSource).toContain('function spanLabel(period: string | undefined = shownSpan): string {');
        expect(speciesSource).toContain('data-leaderboard-analytics-window>{spanLabel(timelineSpan)}');
        expect(speciesSource).not.toMatch(/data-leaderboard-rankings-window>\{spanLabel\(\)\} · \{span ===/);
    });

    it('asks a Today load again when its answers counted from different midnights', () => {
        expect(speciesSource).toContain('const MAX_TODAY_RELOADS = 2;');
        expect(speciesSource).toContain("if (requestedSpan === 'today' && !windowsAgree([rankingStart, audioStart])) {");
        expect(speciesSource).toContain("if (requestedSpan === 'today' && !windowsAgree(chartStarts)) {");
        // Out of tries, a straddled Today is refused rather than shown.
        expect(speciesSource).toMatch(/if \(attempt < MAX_TODAY_RELOADS\) return loadLeaderboardAttempt\(attempt \+ 1\);\s*refuseStraddledToday\(loadGeneration\);/);
    });

    it('commits Seen and Heard together, and keeps the overlays on the accepted window', () => {
        expect(speciesSource).toMatch(/const \[rankingResult, audioResult\] = await Promise\.allSettled\(\[/);
        expect(speciesSource).not.toMatch(/loading = true;\s*error = null;\s*leaderboardWindow = null;/);
        expect(speciesSource).toContain("let acceptedTodayStart = $derived(loadedSpan === 'today' ? (leaderboardWindow?.start ?? null) : null);");
        expect(speciesSource).toContain('portraits = todayStart && !windowsAgree([todayStart, response.window_start]) ? [] : response.portraits;');
        expect(speciesSource).toContain('if (todayStart && !windowsAgree([todayStart, response.window_start])) {');
        expect(speciesSource).toContain('if (wallFetched.span !== loadedSpan) return [];');
    });

    it('states the start a guest window was cut to', () => {
        expect(speciesSource).toContain('shortenedWindowStart(sourceMode, seenWindowReading, heardWindowReading)');
        expect(speciesSource).toContain('data-leaderboard-window-shortened');
        expect(en.window_shortened_note).toContain('{time}');
    });

    it('withholds the trend with the reason the server measured', () => {
        expect(speciesSource).toContain("trendGap(sourceMode, seenWindowReading, heardWindowReading)");
        for (const [gap, key] of [['clock_change', 'clock'], ['shared_window', 'shared'], ['cleanup', 'cleanup']]) {
            expect(speciesSource).toMatch(new RegExp(`currentTrendGap === '${gap}'\\}\\s*<p[^>]*>\\s*\\{\\$_\\('leaderboard\\.trend_not_comparable_${key}'`));
        }
        // Whether the viewer is a guest says nothing about why the trend is missing.
        expect(speciesSource).not.toContain("authStore.isGuest\n                        ? $_('leaderboard.trend_not_comparable");
        expect(speciesSource).toMatch(/currentTrendGap === 'history' && trendHistoryStart/);
    });
});
