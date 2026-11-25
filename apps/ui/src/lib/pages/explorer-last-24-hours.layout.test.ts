import { describe, expect, it } from 'vitest';

import eventsSource from './Events.svelte?raw';
import dashboardSource from './Dashboard.svelte?raw';
import filtersSource from '../components/ExplorerFilters.svelte?raw';
import fieldLogSource from '../components/FieldLog.svelte?raw';

/** The opening tag of the element carrying `marker`, attributes included. */
function tagWith(source: string, marker: string): string {
    const at = source.indexOf(marker);
    expect(at).toBeGreaterThan(-1);
    const start = source.lastIndexOf('<', at);
    return source.slice(start, source.indexOf('>', at) + 1);
}

describe('the Explorer reads the last 24 hours as one window (#1098)', () => {
    it('offers Last 24 hours beside the calendar presets', () => {
        expect(filtersSource).toContain("const datePresets: DatePreset[] = ['all', '24h', 'today', 'week', 'month', 'custom'];");
        expect(filtersSource).toContain("'24h': { key: 'last_24_hours', fallback: 'Last 24 hours' }");
    });

    it('fixes one pair of instants when a read begins, and only for the rolling window', () => {
        expect(eventsSource).toContain('let timeWindow = $derived(explorerWindow(datePreset, dateRange, windowNow));');
        expect(eventsSource).toContain("if (datePreset === '24h') windowNow = new Date();");
        expect(eventsSource.indexOf("if (datePreset === '24h') windowNow = new Date();")).toBeLessThan(eventsSource.indexOf('const range = timeWindow;'));
    });

    it('sends that window to the visits, the captures and their count', () => {
        // fetchVisits, fetchEvents and fetchEventsCount each spread the same request window.
        expect(eventsSource.match(/\.\.\.range\.request,/g)).toHaveLength(3);
        expect(eventsSource).not.toMatch(/startDate: range\.start/);
    });

    it('gives a visit\'s captures, Garden and the heard calls the same instants', () => {
        expect(eventsSource).toContain('const captureWindow = $derived({ ...timeWindow.request, onlyHidden: showHidden });');
        expect(eventsSource.match(/rangeStart: timeWindow\.start,/g)).toHaveLength(2);
        expect(eventsSource).toContain('start: range.start?.toISOString() ?? null,');
        expect(eventsSource).toContain('start: timeWindow.start?.toISOString() ?? null,');
        // No read works the window out from the calendar days on its own any more.
        expect(eventsSource).not.toContain('localDayBound(dateRange');
    });
});

describe('the field log links to the whole history and to its own window separately (#1098)', () => {
    it('keeps the header link on the whole history', () => {
        expect(fieldLogSource).toMatch(/<button\s+onclick=\{\(\) => onseeall\?\.\(\)\}/);
        expect(dashboardSource).toContain("onseeall={() => onnavigate?.(gardenVisits.length > 0 ? '/events?visitors=all' : '/events')}");
    });

    it('opens the truncation line on the last 24 hours with the visitors named', () => {
        expect(tagWith(fieldLogSource, 'data-field-log-more')).toContain('onclick={() => onseewindow?.()}');
        expect(dashboardSource).toContain('onseewindow={() => onnavigate?.(fieldLogWindowLink(gardenAvailable))}');
    });
});
