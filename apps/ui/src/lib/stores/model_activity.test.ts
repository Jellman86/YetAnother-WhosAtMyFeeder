import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ActivityPhase } from '../settings/model-readiness';
import { ACTIVE_POLL_MS, GARDEN_CHECK_MODEL, IDLE_POLL_MS, ModelActivityStore } from './model_activity.svelte';

/** A server whose report the test changes, and a count of how often it was asked. */
function server(initial: Record<string, ActivityPhase> = {}) {
    const state = { report: initial, fails: false, reads: 0 };
    const read = async (): Promise<Record<string, ActivityPhase>> => {
        state.reads += 1;
        if (state.fails) throw new Error('offline');
        return { ...state.report };
    };
    return { state, read };
}

describe('work in progress on a model, reconciled with the server from anywhere', () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it('has no phase for a model nothing is being done to', () => {
        const store = new ModelActivityStore(server().read);
        expect(store.phase('small_birds')).toBeNull();
        expect(store.phase(null)).toBeNull();
    });

    it('reads the server as soon as a surface starts watching, and shows work another tab started', async () => {
        const { read } = server({ small_birds: 'downloading' });
        const store = new ModelActivityStore(read);
        const stop = store.watch();
        await vi.advanceTimersByTimeAsync(0);
        expect(store.phase('small_birds')).toBe('downloading');
        stop();
    });

    it('stops saying "downloading" when the download finishes, even though the page that started it has gone', async () => {
        // Models starts a repair and records it; the owner leaves for another page.
        const { state, read } = server();
        const store = new ModelActivityStore(read);
        const models = store.watch();
        store.hint('small_birds', 'downloading');
        state.report = { small_birds: 'downloading' };
        await vi.advanceTimersByTimeAsync(ACTIVE_POLL_MS);
        models();
        // About is open instead, and the download ends on the server.
        const about = store.watch();
        state.report = {};
        await vi.advanceTimersByTimeAsync(ACTIVE_POLL_MS);
        expect(store.phase('small_birds')).toBeNull();
        about();
    });

    it('shows work the moment it is started here, before the server has reported it', () => {
        const store = new ModelActivityStore(server().read);
        store.hint('small_birds', 'validating');
        expect(store.phase('small_birds')).toBe('validating');
    });

    it('forgets a hint the server never confirms', async () => {
        const { read } = server();
        const store = new ModelActivityStore(read);
        const stop = store.watch();
        store.hint('small_birds', 'downloading');
        await vi.advanceTimersByTimeAsync(20_000);
        expect(store.phase('small_birds')).toBeNull();
        stop();
    });

    it('takes back a hint when the work ends here first', () => {
        const store = new ModelActivityStore(server().read);
        store.hint(GARDEN_CHECK_MODEL, 'downloading');
        store.hint(GARDEN_CHECK_MODEL, null);
        expect(store.phase(GARDEN_CHECK_MODEL)).toBeNull();
    });

    it('asks often while work is in progress and seldom while none is', async () => {
        const { state, read } = server({ small_birds: 'downloading' });
        const store = new ModelActivityStore(read);
        const stop = store.watch();
        await vi.advanceTimersByTimeAsync(0);
        const first = state.reads;
        await vi.advanceTimersByTimeAsync(ACTIVE_POLL_MS * 3);
        expect(state.reads - first).toBe(3);
        state.report = {};
        await vi.advanceTimersByTimeAsync(ACTIVE_POLL_MS);
        const quiet = state.reads;
        await vi.advanceTimersByTimeAsync(IDLE_POLL_MS - 1);
        expect(state.reads).toBe(quiet);
        await vi.advanceTimersByTimeAsync(1);
        expect(state.reads).toBe(quiet + 1);
        stop();
    });

    it('asks nothing while no surface is watching, and one watcher leaving does not stop another', async () => {
        const { state, read } = server();
        const store = new ModelActivityStore(read);
        await vi.advanceTimersByTimeAsync(IDLE_POLL_MS * 2);
        expect(state.reads).toBe(0);
        const first = store.watch();
        const second = store.watch();
        first();
        await vi.advanceTimersByTimeAsync(IDLE_POLL_MS);
        expect(state.reads).toBeGreaterThan(1);
        second();
        const stopped = state.reads;
        await vi.advanceTimersByTimeAsync(IDLE_POLL_MS * 3);
        expect(state.reads).toBe(stopped);
    });

    it('claims no work it cannot read: a failed read clears what the server last said', async () => {
        const { state, read } = server({ small_birds: 'downloading' });
        const store = new ModelActivityStore(read);
        const stop = store.watch();
        await vi.advanceTimersByTimeAsync(0);
        expect(store.phase('small_birds')).toBe('downloading');
        state.fails = true;
        await vi.advanceTimersByTimeAsync(ACTIVE_POLL_MS);
        expect(store.phase('small_birds')).toBeNull();
        // And it keeps asking, so the phase returns when the server does.
        state.fails = false;
        await vi.advanceTimersByTimeAsync(IDLE_POLL_MS);
        expect(store.phase('small_birds')).toBe('downloading');
        stop();
    });
});
