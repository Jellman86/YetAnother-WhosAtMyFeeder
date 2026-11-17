import { describe, expect, it } from 'vitest';
import noteSource from './DailyTotalsNote.svelte?raw';
import modalSource from './SpeciesDetailModal.svelte?raw';
import speciesSource from '../pages/Species.svelte?raw';
import enCommon from '../i18n/locales/en/common.json';
import deCommon from '../i18n/locales/de/common.json';
import enDetail from '../i18n/locales/en/species_detail.json';
import deDetail from '../i18n/locales/de/species_detail.json';
import enLeaderboard from '../i18n/locales/en/leaderboard.json';
import enSettings from '../i18n/locales/en/settings.json';
import deSettings from '../i18n/locales/de/settings.json';

describe('a chart says when its older days come from daily totals (#949)', () => {
    it('sits under the Leaderboard chart, inside its figure, from the timeline it drew', () => {
        const figure = speciesSource.indexOf("title={$_('leaderboard.detections_over_time')}");
        const note = speciesSource.indexOf('<DailyTotalsNote coverage={timeline?.daily_totals} />');
        expect(figure).toBeGreaterThan(-1);
        expect(note).toBeGreaterThan(figure);
        expect(note).toBeLessThan(speciesSource.indexOf('</ChartFigure>', figure));
    });

    it('sits under the species weekday and month charts and says the hour chart has no daily totals', () => {
        const activity = modalSource.indexOf('data-species-activity');
        const note = modalSource.indexOf('<DailyTotalsNote');
        expect(note).toBeGreaterThan(activity);
        expect(modalSource.slice(note, note + 260)).toContain('coverage={stats.daily_totals}');
        expect(modalSource.slice(note, note + 260)).toContain("species_detail.daily_totals_time_of_day");
    });

    it('names a local day and shows nothing when the chart counted stored captures only', () => {
        expect(noteSource).toContain('dailyTotalsNote(coverage)');
        expect(noteSource).toContain('{#if note}');
        expect(noteSource).toContain('formatCalendarDay(note.firstStoredDay)');
        expect(noteSource).toContain("<p class=\"mt-3 max-w-prose text-xs leading-snug text-muted\" data-daily-totals-note>{sentences.join(' ')}</p>");
    });

    it('never claims a photo or clip that is gone, in the glossary units', () => {
        expect(enCommon.daily_totals_note).toBe(
            'Counts before {date} come from daily totals; photos and clips from those days are no longer stored.'
        );
        expect(enCommon.daily_totals_partial).toContain('captures');
        expect(enCommon.daily_totals_partial).toContain('visited');
        expect(enDetail.daily_totals_time_of_day).toContain('stored captures only');
        expect(deCommon.daily_totals_note).toContain('Tagessummen');
        expect(deCommon.daily_totals_note).toContain('nicht mehr gespeichert');
        expect(deCommon.daily_totals_partial).toContain('Aufnahmen');
        expect(deCommon.daily_totals_partial).toContain('Besuche');
        expect(deDetail.daily_totals_time_of_day).toContain('gespeicherte Aufnahmen');
        for (const text of [...Object.values(deCommon), deDetail.daily_totals_time_of_day].filter(
            (value): value is string => typeof value === 'string' && value.includes('Tagessumme')
        )) {
            expect(text).not.toMatch(/Erkennung|Sichtung|—/);
        }
    });

    it('lets the hour and weekday heatmap say its older days have no time of day, not that nothing was seen', () => {
        expect(speciesSource).toContain('const heatmapCountsStoredOnly = $derived(Boolean(timeline?.daily_totals?.totals_through));');
        const empty = speciesSource.indexOf('data-heatmap-empty');
        expect(speciesSource.slice(empty, empty + 420)).toContain("leaderboard.no_activity_daily_totals");
        expect(speciesSource).toContain('data-heatmap-stored-only');
        expect(enLeaderboard.no_activity_daily_totals).toContain('not the time of day');
        expect(enLeaderboard.heatmap_stored_only).toContain('stored captures only');
    });

    it('names the daily totals in every Delete all confirmation, where the owner decides', () => {
        for (const key of ['confirm', 'confirm_changed', 'confirm_uncounted'] as const) {
            expect(enSettings.danger[key]).toContain('daily totals');
            expect(deSettings.danger[key]).toContain('Tagessummen');
        }
    });
});
