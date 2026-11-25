import { describe, expect, it } from 'vitest';

import dashboardSource from './Dashboard.svelte?raw';
import dayBarSource from '../components/DayBar.svelte?raw';
import histogramSource from '../components/DailyHistogram.svelte?raw';
import reviewQueueSource from '../components/ReviewQueueCard.svelte?raw';
import recentAudioSource from '../components/RecentAudio.svelte?raw';
import visitorsSource from '../components/TopVisitors.svelte?raw';
import contextSource from '../components/DeskContextCards.svelte?raw';
import fieldLogSource from '../components/FieldLog.svelte?raw';
import statsApiSource from '../api/stats.ts?raw';
import eventsApiSource from '../api/events.ts?raw';

function between(source: string, start: string, end: string): string {
    const from = source.indexOf(start);
    expect(from, start).toBeGreaterThan(-1);
    const to = source.indexOf(end, from + start.length);
    expect(to, end).toBeGreaterThan(from);
    return source.slice(from, to);
}

describe('the Dashboard\'s Today (#1097)', () => {
    it('offers Today beside the last 24 hours at the heading, and names the window it shows', () => {
        expect(dayBarSource).toContain("{ value: 'today', label: $_('dashboard.day_bar.window_today', { default: 'Today' }) }");
        expect(dayBarSource).toContain("{ value: 'rolling', label: $_('dashboard.day_bar.window', { default: 'Last 24 hours' }) }");
        expect(dayBarSource).toContain('<Segmented');
        expect(dayBarSource).toContain("label={$_('dashboard.day_bar.window_choice', { default: 'Period shown' })}");
        const heading = between(dayBarSource, '<h1', '</h1>');
        expect(heading).toContain('{windowName}');
        expect(dayBarSource).toContain("windowKind === 'today'\n            ? $_('dashboard.day_bar.window_today'");
    });

    it('remembers the choice on this device and starts on the last 24 hours', () => {
        expect(dashboardSource).toContain('let windowChoice = $state<DeskWindowKind>(readDeskWindowChoice(() => localStorage));');
        expect(between(dashboardSource, 'function chooseWindow(', '\n    }')).toContain('saveDeskWindowChoice(() => localStorage, next);');
        expect(dashboardSource).toContain('choice={windowChoice}');
        expect(dashboardSource).toContain('onwindowchange={chooseWindow}');
    });

    it('names the window of the figures on screen, never the one still being read', () => {
        expect(dashboardSource).toContain('const deskKind = $derived<DeskWindowKind>(shownWindow?.kind ?? windowChoice);');
        // The window is published with the summary it was read for, and cleared with it.
        expect(dashboardSource).toContain('summary = summaryRes; summaryHour = desk.end.getHours(); shownWindow = desk;');
        expect(dashboardSource).toContain('clear: () => { summary = null; shownWindow = null;');
        for (const prop of [
            '<DayBar',
            '<ReviewQueueCard',
            '<DeskContextCards',
            '<RecentAudio',
            '<DailyHistogram',
            '<TopVisitors'
        ]) {
            expect(between(dashboardSource, prop, '/>')).toContain('windowKind={deskKind}');
        }
    });

    it('clears every reading and drops the reads in flight when the window changes', () => {
        const reread = between(dashboardSource, 'function rereadDesk(): void {', '\n    }');
        const loads = reread.indexOf('void loadSummary();');
        for (const loader of ['summaryLoader', 'audioSummaryLoader', 'reviewQueueLoader', 'speciesChecksLoader']) {
            const at = reread.indexOf(`${loader}.invalidate();`);
            expect(at, loader).toBeGreaterThan(-1);
            expect(at).toBeLessThan(loads);
        }
        expect(reread).toContain('reviewSessionRequest += 1;');
    });

    it('settles one window per load and gives it to every read on the desk', () => {
        const summaryRead = between(dashboardSource, 'const summaryLoader = createObservationProjectionLoader({', 'apply:');
        expect(summaryRead).toContain('const desk = deskWindow(windowChoice, new Date());');
        expect(summaryRead).toContain('fetchDailySummary(desk.kind, signal)');
        expect(summaryRead).toContain("fetchGardenVisits({ start: window.startTime, end: window.endTime, order: 'newest', limit: VISIT_ROW_LIMIT }, signal)");
        expect(summaryRead).toContain("fetchVisits({ ...window, limit: VISIT_ROW_LIMIT, signal, requestKey: 'dashboard:visits' })");
        expect(dashboardSource).toContain('fetchReviewQueue({ limit: REVIEW_QUEUE_READ_LIMIT, window: windowChoice, signal })');
        expect(dashboardSource).toContain('fetchReviewQueue({ limit: REVIEW_SESSION_READ_LIMIT, window: windowChoice })');
        expect(dashboardSource).toContain("const span = windowChoice === 'today' ? 'today' : 'day';");
        expect(dashboardSource).toContain('fetchLeaderboardSpecies(span, signal)');
        expect(dashboardSource).toContain('fetchAudioSpeciesLeaderboard(span, signal)');
        expect(dashboardSource).toContain('fetchAudioSummary({ start_date: desk.start.toISOString(), end_date: desk.end.toISOString() }, signal)');
        expect(statsApiSource).toContain('`${API_BASE}/stats/daily-summary?window=${window}`');
        expect(eventsApiSource).toContain("&window=${options.window ?? 'rolling'}");
    });

    it('keeps live captures inside the window and reads the new day at local midnight', () => {
        expect(dashboardSource).toContain('withinDeskWindow(detectionsStore.detections, now.getTime(), deskWindowStart(deskKind, now))');
        const midnight = between(dashboardSource, "if (windowChoice !== 'today') return;", 'return () => clearTimeout(timer);');
        expect(midnight).toContain('msUntilNextLocalMidnight(new Date()) + 1000');
        expect(midnight).toContain('untrack(rereadDesk);');
    });

    it('says "yet today" only of a Today that was read, and tells a guest where shared history starts', () => {
        // The log shows its empty message only once a read succeeded with nothing in it.
        const loading = fieldLogSource.indexOf('{#if loading && renderRows.length === 0}');
        const empty = fieldLogSource.indexOf('{:else if renderRows.length === 0}');
        const failed = fieldLogSource.indexOf('{:else if unavailable');
        expect(loading).toBeGreaterThan(-1);
        expect(failed).toBeGreaterThan(loading);
        expect(empty).toBeGreaterThan(failed);
        expect(dashboardSource).toContain('emptyMessage={fieldLogEmpty}');
        expect(dashboardSource).toContain('let sharedFrom = $derived(authStore.isGuest && shownWindow ? sharedHistoryStart(shownWindow, summary?.window_start) : null);');
        expect(dayBarSource).toContain('data-day-bar-shared-from');
    });

    it('opens the Explorer on the window the log shows', () => {
        expect(dashboardSource).toContain('hiddenLabel={fieldLogEarlier}');
        expect(dashboardSource).toContain("$_('dashboard.field_log.earlier_today'");
        expect(dashboardSource).toContain('onseewindow={() => onnavigate?.(fieldLogWindowLink(gardenAvailable, deskKind))}');
    });

    it('draws Today from midnight to the current hour', () => {
        expect(histogramSource).toContain("Array.from({ length: currentHour + 1 }, (_, hour) => ({ hour, value: data[hour] ?? 0, isNow: hour === currentHour }))");
        expect(histogramSource).toContain("dashboard.histogram.visits_per_hour_today");
        expect(histogramSource).toContain("dashboard.histogram.aria_today");
    });

    it('words every card for the window it was read for', () => {
        expect(reviewQueueSource).toContain('dashboard.review_queue.empty_today');
        expect(reviewQueueSource).toContain('dashboard.review_queue.visits_clear_today');
        expect(recentAudioSource).toContain('dashboard.desk.heard_empty_today');
        expect(visitorsSource).toContain('dashboard.top_visitors_empty_today');
        for (const source of [recentAudioSource, visitorsSource, contextSource]) {
            expect(source).toContain("windowKind === 'today' ? $_('dashboard.day_bar.window_today', { default: 'Today' })");
        }
    });
});
