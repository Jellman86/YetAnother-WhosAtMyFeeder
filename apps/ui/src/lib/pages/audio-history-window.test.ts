import { afterEach, describe, expect, it, vi } from 'vitest';
import {
    AUDIO_HISTORY_WINDOWS,
    audioHistoryRequest,
    isAudioHistoryWindow,
    msUntilNextLocalMidnight,
    narrowedWindowStart
} from './audio-history-window';
import { DEFAULT_AUDIO_HISTORY_FILTERS, type AudioHistoryFilters } from './audio-history-filters';
import { createAudioHistoryLoader } from './audio-history-loader';
import { audioHeatmapReading, audioSpeciesHeatmapParams } from './audio-heatmap-species';
import type { AudioActivityHeatmapResponse, AudioHistoryResponse, AudioSummaryResponse } from '../api';

afterEach(() => {
    vi.unstubAllEnvs();
});

function request(window: AudioHistoryFilters['window'], now: Date, offset = 0) {
    return audioHistoryRequest(
        { applied: { ...DEFAULT_AUDIO_HISTORY_FILTERS, window }, search: '', onlyHidden: false, offset, pageSize: 25 },
        now
    );
}

describe('audio history windows', () => {
    it('offers Today before the rolling windows and keeps 30 days as the default', () => {
        expect(AUDIO_HISTORY_WINDOWS).toEqual(['today', '24h', '7d', '30d', '90d', '1y']);
        expect(DEFAULT_AUDIO_HISTORY_FILTERS.window).toBe('30d');
    });

    it('accepts only the windows it offers', () => {
        expect(isAudioHistoryWindow('today')).toBe(true);
        expect(isAudioHistoryWindow('7d')).toBe(true);
        expect(isAudioHistoryWindow('1')).toBe(false);
        expect(isAudioHistoryWindow(7)).toBe(false);
    });

    it('asks for the rolling windows by their number of days', () => {
        const now = new Date('2026-11-25T10:30:00Z');
        expect(request('24h', now).list).toMatchObject({ days: 1 });
        expect(request('7d', now).aggregate).toMatchObject({ days: 7 });
        expect(request('1y', now).list.start_date).toBeUndefined();
    });

    it('reads Today from the viewer\'s local midnight to now, as UTC instants', () => {
        vi.stubEnv('TZ', 'America/New_York');
        const now = new Date('2026-11-25T15:42:10.250Z');
        const today = request('today', now);
        // 10:42 in New York; its midnight is 05:00 UTC.
        expect(today.list).toMatchObject({ start_date: '2026-11-25T05:00:00.000Z', end_date: '2026-11-25T15:42:10.250Z' });
        expect(today.list.days).toBeUndefined();
    });

    it('starts Today on the local calendar day even when UTC is already on the next one', () => {
        vi.stubEnv('TZ', 'America/Los_Angeles');
        // 20:00 on 24 November in Los Angeles is 04:00 UTC on 25 November.
        const today = request('today', new Date('2026-11-25T04:00:00Z'));
        expect(today.aggregate.start_date).toBe('2026-11-24T08:00:00.000Z');
    });

    it('sends the same window and filters to the list and its summaries, with paging only on the list', () => {
        const today = request('today', new Date('2026-11-25T10:30:00Z'), 50);
        const { limit, offset, ...listWithoutPaging } = today.list;
        expect({ limit, offset }).toEqual({ limit: 25, offset: 50 });
        expect(listWithoutPaging).toEqual(today.aggregate);
    });

    it('names a Today reading by its day, so a refresh later the same day asks the same question', () => {
        vi.stubEnv('TZ', 'Europe/London');
        const morning = request('today', new Date('2026-11-25T08:00:00Z'));
        const evening = request('today', new Date('2026-11-25T20:00:00Z'));
        const tomorrow = request('today', new Date('2026-11-26T00:00:01Z'));
        expect(evening.key).toBe(morning.key);
        expect(tomorrow.key).not.toBe(morning.key);
        expect(request('24h', new Date('2026-11-25T08:00:00Z')).key).not.toBe(morning.key);
        expect(request('today', new Date('2026-11-25T08:00:00Z'), 25).key).not.toBe(morning.key);
    });

    it('counts down to the next local midnight', () => {
        vi.stubEnv('TZ', 'Europe/Berlin');
        // 23:59:30 in Berlin.
        expect(msUntilNextLocalMidnight(new Date('2026-11-25T22:59:30Z'))).toBe(30_000);
    });

    it('reports a counted start later than the one asked for, and nothing otherwise', () => {
        expect(narrowedWindowStart('2026-11-24T14:00:00.000Z', '2026-11-25T00:00:00Z')).toBe('2026-11-25T00:00:00Z');
        expect(narrowedWindowStart('2026-11-25T05:00:00.000Z', '2026-11-25T05:00:00Z')).toBeNull();
        expect(narrowedWindowStart(undefined, '2026-11-25T00:00:00Z')).toBeNull();
        expect(narrowedWindowStart('2026-11-25T05:00:00.000Z', undefined)).toBeNull();
    });
});

describe('a Today reading', () => {
    const history = { items: [], total: 0, limit: 25, offset: 0 } as AudioHistoryResponse;
    const summary = { total: 0, top_species: [] } as unknown as AudioSummaryResponse;
    const grid = { total_count: 0, max_cell_count: 0, cells: [], window_start: '', window_end: '' } as AudioActivityHeatmapResponse;

    it('settles its instants once, and the list, summary, grid and species grid all ask for them', async () => {
        const clock = vi.fn(() => new Date('2026-11-25T10:30:00Z'));
        const asked: Record<string, { start_date?: string | null; end_date?: string | null }> = {};
        const resolveRequest = vi.fn(() => request('today', clock()));
        const shown: { request?: ReturnType<typeof request> } = {};
        const loader = createAudioHistoryLoader({
            resolveRequest,
            requestKey: (r) => r.key,
            fetchHistory: async (r) => { asked.history = r.list; clock.mockReturnValue(new Date('2026-11-25T10:30:05Z')); return history; },
            fetchSummary: async (r) => { asked.summary = r.aggregate; return summary; },
            fetchHeatmap: async (r) => { asked.heatmap = r.aggregate; return grid; },
            begin: vi.fn(),
            apply: (_h, _s, _g, r) => { shown.request = r; },
            clear: vi.fn(),
            fail: vi.fn(),
            finish: vi.fn()
        });

        await loader.load();

        expect(resolveRequest).toHaveBeenCalledTimes(1);
        const applied = shown.request;
        if (!applied) throw new Error('The reading was not applied');
        const drillDown = audioSpeciesHeatmapParams(audioHeatmapReading(applied.aggregate), 'Erithacus rubecula');
        const bounds = (value: { start_date?: string | null; end_date?: string | null }) => [value.start_date, value.end_date];
        const expected = [applied.list.start_date, applied.list.end_date];
        expect(expected[0]).toBeTruthy();
        expect(bounds(asked.history)).toEqual(expected);
        expect(bounds(asked.summary)).toEqual(expected);
        expect(bounds(asked.heatmap)).toEqual(expected);
        expect(bounds(drillDown)).toEqual(expected);
    });

    it('never lands over a window chosen after it, however late it answers', async () => {
        let releaseToday: (value: AudioHistoryResponse) => void = () => undefined;
        const windows: AudioHistoryFilters['window'][] = ['today', '7d'];
        const apply = vi.fn();
        const loader = createAudioHistoryLoader({
            resolveRequest: () => request(windows.shift() ?? '7d', new Date('2026-11-25T10:30:00Z')),
            requestKey: (r) => r.key,
            fetchHistory: (r) => (r.list.start_date ? new Promise((resolve) => { releaseToday = resolve; }) : Promise.resolve(history)),
            fetchSummary: async () => summary,
            fetchHeatmap: async () => grid,
            begin: vi.fn(),
            apply,
            clear: vi.fn(),
            fail: vi.fn(),
            finish: vi.fn()
        });

        const today = loader.load();
        await loader.load();
        releaseToday(history);
        await today;

        expect(apply).toHaveBeenCalledTimes(1);
        expect(apply.mock.calls[0][3].list).toMatchObject({ days: 7 });
    });
});
