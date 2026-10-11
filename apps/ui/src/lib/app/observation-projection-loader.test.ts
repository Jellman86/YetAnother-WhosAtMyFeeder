import { expect, it, vi } from 'vitest';
import { createObservationProjectionLoader } from './observation-projection-loader';

it('retires previously public species totals and cannot restore them from an older response', async () => {
    let state = { species: 'Hidden species', count: 9 };
    let releaseOld: (value: typeof state) => void = () => undefined;
    const fetch = vi.fn().mockImplementationOnce(() => new Promise((resolve) => { releaseOld = resolve; }))
        .mockResolvedValueOnce({ species: 'Public species', count: 2 });
    const loader = createObservationProjectionLoader({ fetch, apply: (value: typeof state) => { state = value; }, clear: () => { state = { species: '', count: 0 }; }, fail: vi.fn() });
    const oldLoad = loader.load(); loader.invalidate();
    expect(state).toEqual({ species: '', count: 0 });
    await loader.load(); releaseOld({ species: 'Hidden species', count: 9 }); await oldLoad;
    expect(state).toEqual({ species: 'Public species', count: 2 });
});

it('does not run failure/settled callbacks for an aborted older projection', async () => {
    let rejectOld: (error: Error) => void = () => undefined;
    const fetch = vi.fn().mockImplementationOnce(() => new Promise((_, reject) => { rejectOld = reject; })).mockResolvedValueOnce(2);
    const fail = vi.fn(); const settled = vi.fn(); const apply = vi.fn();
    const loader = createObservationProjectionLoader({ fetch, apply, clear: vi.fn(), fail, settled });
    const oldLoad = loader.load(); await loader.load(); rejectOld(new Error('cancelled')); await oldLoad;
    expect(fail).not.toHaveBeenCalled(); expect(settled).toHaveBeenCalledTimes(1); expect(apply).toHaveBeenCalledWith(2);
});

it('keeps explicitly invalidated data empty after failure and ignores responses after disposal', async () => {
    let state: number | null = 9;
    const fail = vi.fn(); const apply = vi.fn((value: number) => { state = value; });
    const loader = createObservationProjectionLoader({ fetch: vi.fn().mockRejectedValue(new Error('503')), apply, clear: () => { state = null; }, fail });
    loader.invalidate(); await loader.load(); expect(state).toBeNull(); expect(fail).toHaveBeenCalledTimes(1);
    let release: (value: number) => void = () => undefined;
    const disposed = createObservationProjectionLoader({ fetch: () => new Promise<number>((resolve) => { release = resolve; }), apply, clear: vi.fn(), fail });
    const pending = disposed.load(); disposed.dispose(); release(9); await pending; expect(apply).not.toHaveBeenCalled();
});
