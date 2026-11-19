import { describe, expect, it } from 'vitest';
import source from './AudioHistory.svelte?raw';
import chartSeries from './audio-chart-series.ts?raw';
import enAudio from '../i18n/locales/en/audio.json';

describe('Audio history keeps loading, measured-empty, failed and stale apart', () => {
    it('shows a figure only for a reading, never a zero for a pending or failed read', () => {
        expect(source).toContain('audioReading({ loading, error, stale, total: summary?.total ?? null })');
        expect(source).toContain('{#snippet statValue(value: string)}');
        expect(source).toContain('data-audio-stat-pending');
        expect(source).toContain('data-audio-stat-unavailable');
        // No stat writes its zero straight into the page.
        expect(source).not.toMatch(/<dd[^>]*>\{\(summary\?\.total \?\? 0\)/);
        expect(source).not.toMatch(/<dd[^>]*>\{summary\?\.(species|source)_count \?\? 0\}/);
    });

    it('says a failed read in its own words with a next step, the server text only as a detail', () => {
        expect(source).toContain('data-audio-read-failed');
        expect(enAudio.history.read_failed).toContain('could not be read');
        expect(enAudio.history.read_failed_next).toContain('Try again');
        expect(source).toContain('{@render technicalDetails(error)}');
        expect(source).not.toMatch(/<span>\{error\}<\/span>/);
    });

    it('keeps a stale reading on screen with its time, and says no activity only when measured', () => {
        expect(source).toContain('data-audio-stale');
        expect(source).toContain("{#if !measured}");
        expect(source).toContain('data-audio-chart-unavailable');
    });

    it('gives every chart its numbers as text, including the other species', () => {
        // Each chart is a ChartFigure, whose table holds its numbers.
        expect(source.match(/<ChartFigure\b/g)?.length).toBe(3);
        expect(source.match(/table=\{measured && has(?:Daily|Heatmap|Species) \?/g)?.length).toBe(3);
        expect(source).toContain('data-audio-mix-count');
        expect(source).toContain('speciesMix.map((item) => [item.species, item.count.toLocaleString()])');
    });

    it('draws each chart and lists its numbers from one series, so a chart and its table always agree', () => {
        expect(source).toContain('dailySeries(summary?.daily_counts ?? []');
        expect(source).toContain('dailyPoints.map((point) => [point.label, point.count.toLocaleString()])');
        expect(source).toContain('weekdayHourTable(heatmap?.cells ?? []');
        expect(source).not.toContain('T12:00:00Z');
    });

    it('shows the hour of day as the weekday-by-hour grid of calls heard, read with the summary', () => {
        expect(source).toContain('fetchHeatmap: () => fetchAudioActivityHeatmap(requestParams(false))');
        expect(source).toContain('<ActivityHeatmap cells={heatmap.cells}');
        expect(source).toContain('unit="calls"');
        // The busiest hour is the grid's, in the viewer's zone, not the summary's UTC hours.
        expect(source).toContain('busiestHourOfDay(heatmap?.cells ?? [])');
    });

    it('leaves nothing of the hour bar chart the grid replaced', () => {
        for (const gone of ['hourlyChartConfig', 'hourlySeries', 'hourlyPoints', 'hasHourly', 'peakHour', 'hourly_counts', "audio.chart.hourly_title", "audio.stat.peak_hour"]) {
            expect(source, gone).not.toContain(gone);
        }
        expect(chartSeries).not.toContain('hourlySeries');
        expect(enAudio.chart).not.toHaveProperty('hourly_title');
        expect(enAudio.chart).not.toHaveProperty('col_hour');
        expect(enAudio.stat).not.toHaveProperty('peak_hour');
        // Two canvases remain: calls over time and the species ring.
        expect(source.match(/<canvas use:chartjs=/g)?.length).toBe(2);
    });

    it('fetches reference photos for the top species only once that list comes near the screen', () => {
        expect(source).toContain('use:whenNearViewport={() => (topSpeciesNear = true)}');
        expect(source).toContain('if (!topSpeciesNear) return;');
    });
});
