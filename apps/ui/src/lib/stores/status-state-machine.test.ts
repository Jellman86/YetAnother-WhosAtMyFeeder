import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SystemStatus } from '../api/status';
import { READ_RETRY_MS, createRetryingReader } from '../app/retrying-reader';
import type { PollDocument } from '../app/visible-poll';
import { STATUS_STALE_AFTER_MS, SystemStatusStore } from './system_status.svelte';

/**
 * Random sequences of what the status store and the retrying reader live through, checked after
 * every step against the rules they promise. A failing seed is printed; rerun it to replay.
 */

function rng(seed: number): () => number {
    let state = seed >>> 0;
    return () => {
        state = (state + 0x6d2b79f5) >>> 0;
        let t = state;
        t = Math.imul(t ^ (t >>> 15), t | 1);
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

const visibleTab: PollDocument = { hidden: false, addEventListener: () => undefined, removeEventListener: () => undefined };

function snapshot(revision: number): SystemStatus {
    return {
        revision, generated_at: 't', startup_instance_id: 'machine', version: 'v',
        overall: { state: 'ok', cause: 'ok', subsystem: null }, subsystems: [],
        jobs_summary: { running: 0, queued: 0, progress: null },
        jobs: { captured_at: 't', items: [], lanes: [] },
        analysis: { pending: 0, active: 0, circuit_open: false },
        model: { state: 'ok', cause: 'ready', revision: 'm' },
        connections: { mqtt: { state: 'connected', server: 'm', port: 1 }, frigate: { state: 'reachable', url: 'f' }, generated_at: 't' },
        diagnostics_revision: 0, incident_revision: 'i', health_revision: 'h'
    };
}

interface Pending { settle: (ok: boolean) => void; old: boolean }

afterEach(() => vi.useRealTimers());

describe('the status store, under random sequences', () => {
    it('is stale exactly when no snapshot was accepted for the threshold, reads one at a time, and is still after clear', async () => {
        vi.useFakeTimers();
        for (let seed = 1; seed <= 60; seed += 1) {
            const random = rng(seed);
            let revision = 0;
            let inFlight = 0;
            let pending: Pending | null = null;
            // Recorded, not thrown: the store catches whatever its read throws.
            const violations: string[] = [];
            const fetch = vi.fn((signal: AbortSignal) => {
                inFlight += 1;
                if (inFlight > 1) violations.push(`seed ${seed}: two reads in flight`);
                return new Promise<SystemStatus>((resolve, reject) => {
                    let settled = false;
                    const settle = (ok: boolean): void => {
                        if (settled) return;
                        settled = true;
                        inFlight -= 1;
                        if (ok) resolve(snapshot(++revision));
                        else reject(new Error('HTTP 502'));
                    };
                    // An aborted read ends there, as a real request does.
                    signal.addEventListener('abort', () => settle(false));
                    pending = { old: false, settle };
                });
            });
            const store = new SystemStatusStore({ fetch, tab: visibleTab });
            let freshSince = Date.now();
            store.start();

            for (let step = 0; step < 80; step += 1) {
                const action = Math.floor(random() * 7);
                const current = pending as Pending | null;
                if (action === 0) store.setStreamLive(true);
                else if (action === 1) store.setStreamLive(false);
                else if (action === 2) {
                    store.ingest(snapshot(++revision));
                    freshSince = Date.now();
                } else if (action === 3 && current) {
                    pending = null;
                    const before = store.snapshot;
                    current.settle(true);
                    await vi.advanceTimersByTimeAsync(0);
                    if (current.old) expect(store.snapshot, `seed ${seed}: a read from before clear changes nothing`).toBe(before);
                    else freshSince = Date.now();
                } else if (action === 4 && current) {
                    pending = null;
                    current.settle(false);
                    await vi.advanceTimersByTimeAsync(0);
                } else if (action === 5) {
                    // An access change: everything read for the old session is dropped, then following restarts.
                    if (current) current.old = true;
                    store.clear();
                    expect(store.snapshot).toBeNull();
                    expect(store.stale).toBe(false);
                    store.start();
                    freshSince = Date.now();
                } else {
                    const before = Date.now();
                    await vi.advanceTimersByTimeAsync(Math.floor(random() * 40_000) + 1);
                    // A read the deadline started during the wait, answered at once, counts from its answer.
                    if (pending && Date.now() - before > 0 && random() < 0.3) {
                        const answered = pending as Pending;
                        pending = null;
                        answered.settle(true);
                        await vi.advanceTimersByTimeAsync(0);
                        if (!answered.old) freshSince = Date.now();
                    }
                }
                expect(store.stale, `seed ${seed} step ${step}`).toBe(Date.now() - freshSince >= STATUS_STALE_AFTER_MS);
                expect(violations, `seed ${seed} step ${step}`).toEqual([]);
            }
            store.clear();
            const stray = pending as Pending | null;
            if (stray) stray.settle(true);
            await vi.advanceTimersByTimeAsync(STATUS_STALE_AFTER_MS * 3);
            expect(store.snapshot, `seed ${seed}: nothing updates after clear`).toBeNull();
            expect(store.stale).toBe(false);
        }
    });

    it('goes stale on reconnects that never bring a snapshot, and reads again', async () => {
        vi.useFakeTimers();
        const fetch = vi.fn(async () => { throw new Error('HTTP 502'); });
        const store = new SystemStatusStore({ fetch, tab: visibleTab });
        store.start();
        for (let cycle = 0; cycle < 10; cycle += 1) {
            store.setStreamLive(true);
            await vi.advanceTimersByTimeAsync(20_000);
            store.setStreamLive(false);
            await vi.advanceTimersByTimeAsync(1_000);
        }
        expect(store.stale).toBe(true);
        expect(fetch.mock.calls.length).toBeGreaterThan(1);
        store.clear();
    });
});

describe('the retrying reader, under random sequences', () => {
    it('reads one at a time, never sooner than the backoff after a failure, and nothing from before a cancel', async () => {
        vi.useFakeTimers();
        for (let seed = 1; seed <= 60; seed += 1) {
            const random = rng(seed * 7919);
            let inFlight = 0;
            let wanted = true;
            let failures = 0;
            let earliestNext = 0;
            let pending: Pending | null = null;
            let cancelledAt = -1;
            let requestedAfterCancel = false;
            // Recorded, not thrown: the reader catches whatever its read throws.
            const violations: string[] = [];
            const read = vi.fn(() => {
                const now = Date.now();
                inFlight += 1;
                if (inFlight > 1) violations.push(`two reads in flight at ${now}`);
                if (now < earliestNext) violations.push(`read at ${now}, before the retry deadline ${earliestNext}`);
                if (cancelledAt >= 0 && !requestedAfterCancel) violations.push(`read at ${now} after a cancel, without a request`);
                return new Promise<boolean>((resolve) => {
                    pending = {
                        old: false,
                        settle: (ok) => {
                            inFlight -= 1;
                            if (!pending || !pending.old) {
                                if (ok) {
                                    failures = 0;
                                    earliestNext = 0;
                                } else if (wanted) {
                                    earliestNext = Date.now() + READ_RETRY_MS[Math.min(failures, READ_RETRY_MS.length - 1)];
                                    failures += 1;
                                }
                            }
                            resolve(ok);
                        }
                    };
                });
            });
            const reader = createRetryingReader({ read, active: () => wanted });

            for (let step = 0; step < 80; step += 1) {
                const action = Math.floor(random() * 6);
                const current = pending as Pending | null;
                if (action === 0 || action === 1) {
                    if (cancelledAt >= 0) requestedAfterCancel = true;
                    reader.request();
                    await vi.advanceTimersByTimeAsync(0);
                } else if (action === 2 && current) {
                    current.settle(random() < 0.5);
                    pending = null;
                    await vi.advanceTimersByTimeAsync(0);
                } else if (action === 3) {
                    if (current) current.old = true;
                    reader.cancel();
                    cancelledAt = Date.now();
                    requestedAfterCancel = false;
                    failures = 0;
                    earliestNext = 0;
                    if (current) {
                        current.settle(false);
                        pending = null;
                    }
                    inFlight = 0;
                } else if (action === 4) {
                    wanted = random() < 0.8;
                } else {
                    await vi.advanceTimersByTimeAsync(Math.floor(random() * 20_000) + 1);
                }
                expect(violations, `seed ${seed} step ${step}`).toEqual([]);
            }
            reader.cancel();
        }
    });
});
