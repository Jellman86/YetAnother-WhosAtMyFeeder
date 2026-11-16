import { expect, it, vi } from 'vitest';
import { createAudioHistoryLoader } from './audio-history-loader';
import type { AudioHistoryResponse, AudioSummaryResponse } from '../api';

const history = (species: string) => ({ items: [{ species }] } as AudioHistoryResponse);
const summary = (species: string) => ({ top_species: [{ species }] } as AudioSummaryResponse);

it('withdraws invalidated audio rows, summary and selection before fetching, then restores public data', async () => {
    let state = { history: history('Hidden bird') as AudioHistoryResponse | null, summary: summary('Hidden bird') as AudioSummaryResponse | null, selected: 'Hidden bird' as string | null };
    let release: (value: AudioHistoryResponse) => void = () => undefined;
    const loader = createAudioHistoryLoader({ fetchHistory: () => new Promise((resolve) => { release = resolve; }), fetchSummary: async () => summary('Public bird'), begin: vi.fn(), apply: (rows, totals) => { state.history = rows; state.summary = totals; }, clear: () => { state = { history: null, summary: null, selected: null }; }, fail: vi.fn(), finish: vi.fn() });
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
    const loader = createAudioHistoryLoader({ fetchHistory, fetchSummary: async () => summary('Public bird'), begin: vi.fn(), apply, clear, fail, finish });
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
    const loader = createAudioHistoryLoader({ fetchHistory: () => new Promise((resolve) => { release = resolve; }), fetchSummary: async () => summary('Old bird'), begin: vi.fn(), apply, clear: vi.fn(), fail: vi.fn(), finish });
    const request = loader.load(); loader.dispose(); release(history('Old bird')); await request;
    expect(apply).not.toHaveBeenCalled(); expect(finish).not.toHaveBeenCalled();
});

it('keeps the last reading, marked stale, when the same request fails on refresh', async () => {
    let key = 'days=7';
    const fetchHistory = vi.fn().mockResolvedValueOnce(history('Robin')).mockRejectedValueOnce(new Error('500'));
    const apply = vi.fn(); const clear = vi.fn(); const fail = vi.fn();
    const loader = createAudioHistoryLoader({ requestKey: () => key, fetchHistory, fetchSummary: async () => summary('Robin'), begin: vi.fn(), apply, clear, fail, finish: vi.fn() });
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
    const loader = createAudioHistoryLoader({ requestKey: () => key, fetchHistory, fetchSummary: async () => summary('Robin'), begin: vi.fn(), apply: vi.fn(), clear, fail, finish: vi.fn() });
    await loader.load();
    key = 'days=30';
    await loader.load();
    expect(clear).toHaveBeenCalledTimes(1);
    expect(fail).toHaveBeenCalledWith(expect.any(Error), { stale: false });
});
