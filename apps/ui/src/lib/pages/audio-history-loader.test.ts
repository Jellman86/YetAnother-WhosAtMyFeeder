import { expect, it, vi } from 'vitest';
import { createAudioHistoryLoader } from './audio-history-loader';
import type { AudioActivityHeatmapResponse, AudioHistoryResponse, AudioSummaryResponse } from '../api';

const history = (species: string) => ({ items: [{ species }] } as AudioHistoryResponse);
const summary = (species: string) => ({ top_species: [{ species }] } as AudioSummaryResponse);
const grid = (total: number) => ({ total_count: total, max_cell_count: total, cells: [], window_start: '', window_end: '' } as AudioActivityHeatmapResponse);

it('withdraws invalidated audio rows, summary and selection before fetching, then restores public data', async () => {
    let state = { history: history('Hidden bird') as AudioHistoryResponse | null, summary: summary('Hidden bird') as AudioSummaryResponse | null, selected: 'Hidden bird' as string | null };
    let release: (value: AudioHistoryResponse) => void = () => undefined;
    const loader = createAudioHistoryLoader({ fetchHistory: () => new Promise((resolve) => { release = resolve; }), fetchSummary: async () => summary('Public bird'), fetchHeatmap: async () => grid(1), begin: vi.fn(), apply: (rows, totals) => { state.history = rows; state.summary = totals; }, clear: () => { state = { history: null, summary: null, selected: null }; }, fail: vi.fn(), finish: vi.fn() });
    const request = loader.load(true);
    expect(state).toEqual({ history: null, summary: null, selected: null });
    release(history('Public bird'));
    await request;
    expect(state.history?.items[0].species).toBe('Public bird');
    expect(state.summary?.top_species[0].species).toBe('Public bird');
});

it('cannot restore hidden audio or settle newer loading when an earlier response finishes', async () => {
    let release: (value: AudioHistoryResponse) => void = () => undefined;
    const fetchHistory = vi.fn().mockImplementationOnce(() => new Promise((resolve) => { release = resolve; })).mockRejectedValueOnce(new Error('503'));
    const apply = vi.fn(); const clear = vi.fn(); const fail = vi.fn(); const finish = vi.fn();
    const loader = createAudioHistoryLoader({ fetchHistory, fetchSummary: async () => summary('Public bird'), fetchHeatmap: async () => grid(1), begin: vi.fn(), apply, clear, fail, finish });
    const previous = loader.load();
    await loader.load(true);
    release(history('Hidden bird'));
    await previous;
    expect(apply).not.toHaveBeenCalled();
    expect(clear).toHaveBeenCalledTimes(2);
    expect(fail).toHaveBeenCalledTimes(1);
    expect(finish).toHaveBeenCalledTimes(1);
});

it('ignores a response after the page is disposed', async () => {
    let release: (value: AudioHistoryResponse) => void = () => undefined;
    const apply = vi.fn(); const finish = vi.fn();
    const loader = createAudioHistoryLoader({ fetchHistory: () => new Promise((resolve) => { release = resolve; }), fetchSummary: async () => summary('Old bird'), fetchHeatmap: async () => grid(1), begin: vi.fn(), apply, clear: vi.fn(), fail: vi.fn(), finish });
    const request = loader.load(); loader.dispose(); release(history('Old bird')); await request;
    expect(apply).not.toHaveBeenCalled(); expect(finish).not.toHaveBeenCalled();
});

it('keeps the last reading, marked stale, when the same request fails on refresh', async () => {
    let key = 'days=7';
    const fetchHistory = vi.fn().mockResolvedValueOnce(history('Robin')).mockRejectedValueOnce(new Error('500'));
    const apply = vi.fn(); const clear = vi.fn(); const fail = vi.fn();
    const loader = createAudioHistoryLoader({ requestKey: () => key, fetchHistory, fetchSummary: async () => summary('Robin'), fetchHeatmap: async () => grid(1), begin: vi.fn(), apply, clear, fail, finish: vi.fn() });
    await loader.load();
    await loader.load();
    // Nothing that was read is withdrawn; the page says it may be out of date.
    expect(clear).not.toHaveBeenCalled();
    expect(fail).toHaveBeenCalledWith(expect.any(Error), { stale: true });
    void key;
});

it('clears instead of showing another window as current when a different request fails', async () => {
    let key = 'days=7';
    const fetchHistory = vi.fn().mockResolvedValueOnce(history('Robin')).mockRejectedValueOnce(new Error('500'));
    const clear = vi.fn(); const fail = vi.fn();
    const loader = createAudioHistoryLoader({ requestKey: () => key, fetchHistory, fetchSummary: async () => summary('Robin'), fetchHeatmap: async () => grid(1), begin: vi.fn(), apply: vi.fn(), clear, fail, finish: vi.fn() });
    await loader.load();
    key = 'days=30';
    await loader.load();
    expect(clear).toHaveBeenCalledTimes(1);
    expect(fail).toHaveBeenCalledWith(expect.any(Error), { stale: false });
});

it('reads the call grid in the same request as the list and summary', async () => {
    const apply = vi.fn();
    const loader = createAudioHistoryLoader({ fetchHistory: async () => history('Robin'), fetchSummary: async () => summary('Robin'), fetchHeatmap: async () => grid(4), begin: vi.fn(), apply, clear: vi.fn(), fail: vi.fn(), finish: vi.fn() });
    await loader.load();
    expect(apply).toHaveBeenCalledWith(history('Robin'), summary('Robin'), { heatmap: grid(4) });
});

it('keeps the list and summary when only the grid cannot be read, and says the grid failed', async () => {
    const failure = new Error('503');
    const apply = vi.fn(); const clear = vi.fn(); const fail = vi.fn();
    const loader = createAudioHistoryLoader({ requestKey: () => 'days=30', fetchHistory: async () => history('Robin'), fetchSummary: async () => summary('Robin'), fetchHeatmap: async () => { throw failure; }, begin: vi.fn(), apply, clear, fail, finish: vi.fn() });
    await loader.load();
    expect(apply).toHaveBeenCalledWith(history('Robin'), summary('Robin'), { error: failure });
    expect(clear).not.toHaveBeenCalled();
    expect(fail).not.toHaveBeenCalled();
});

it('ignores an older grid answer once a newer request has started', async () => {
    let releaseOld: (value: AudioActivityHeatmapResponse) => void = () => undefined;
    const fetchHeatmap = vi.fn()
        .mockImplementationOnce(() => new Promise((resolve) => { releaseOld = resolve; }))
        .mockResolvedValueOnce(grid(9));
    const apply = vi.fn();
    const loader = createAudioHistoryLoader({ fetchHistory: async () => history('Robin'), fetchSummary: async () => summary('Robin'), fetchHeatmap, begin: vi.fn(), apply, clear: vi.fn(), fail: vi.fn(), finish: vi.fn() });
    const older = loader.load();
    await loader.load();
    releaseOld(grid(1));
    await older;
    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledWith(history('Robin'), summary('Robin'), { heatmap: grid(9) });
});

it('withdraws the grid with the list when the list itself cannot be read for a new request', async () => {
    let key = 'days=7';
    const fetchHistory = vi.fn().mockResolvedValueOnce(history('Robin')).mockRejectedValueOnce(new Error('500'));
    const apply = vi.fn(); const clear = vi.fn(); const fail = vi.fn();
    const loader = createAudioHistoryLoader({ requestKey: () => key, fetchHistory, fetchSummary: async () => summary('Robin'), fetchHeatmap: async () => grid(4), begin: vi.fn(), apply, clear, fail, finish: vi.fn() });
    await loader.load();
    key = 'days=30';
    await loader.load();
    expect(apply).toHaveBeenCalledTimes(1);
    expect(clear).toHaveBeenCalledTimes(1);
    expect(fail).toHaveBeenCalledWith(expect.any(Error), { stale: false });
});
