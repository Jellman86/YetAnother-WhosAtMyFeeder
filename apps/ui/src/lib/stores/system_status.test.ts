import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SystemStatus } from '../api/status';
import { isSystemStatus } from '../api/status';
import type { PollDocument } from '../app/visible-poll';
import {
    STATUS_FALLBACK_READ_MS,
    STATUS_STALE_AFTER_MS,
    SystemStatusStore,
    statusNotificationCause,
    telemetrySampleFrom,
    verdictFor
} from './system_status.svelte';

function snapshot(overrides: Partial<SystemStatus> = {}): SystemStatus {
    return {
        revision: 1,
        generated_at: '2026-11-16T09:00:00Z',
        startup_instance_id: 'instance-1',
        version: '2.24.0',
        overall: { state: 'ok', cause: 'ok', subsystem: null },
        subsystems: [
            { key: 'mqtt', state: 'ok', cause: 'connected' },
            { key: 'frigate', state: 'ok', cause: 'reachable' }
        ],
        jobs_summary: { running: 0, queued: 0, progress: null },
        jobs: { captured_at: '2026-11-16T09:00:00Z', items: [], lanes: [] },
        analysis: { pending: 0, active: 0, circuit_open: false },
        model: { state: 'ok', cause: 'ready', revision: 'abc' },
        connections: {
            mqtt: { state: 'connected', server: 'mqtt', port: 1883 },
            frigate: { state: 'reachable', url: 'http://frigate:5000' },
            generated_at: '2026-11-16T09:00:00Z'
        },
        cameras: null,
        telemetry: null,
        diagnostics_revision: 0,
        health_revision: 'h1',
        ...overrides
    };
}

function fakeTab(): PollDocument {
    return { hidden: false, addEventListener: () => undefined, removeEventListener: () => undefined };
}

/** The server's cadence: a push every 15 s for as long as the stream is healthy. */
async function pushEvery15s(store: SystemStatusStore, totalMs: number): Promise<void> {
    for (let elapsed = 0; elapsed < totalMs; elapsed += 15_000) {
        await vi.advanceTimersByTimeAsync(15_000);
        store.ingest(snapshot());
    }
}

afterEach(() => {
    vi.useRealTimers();
});

describe('SystemStatusStore', () => {
    it('keeps the newest revision when a slow read lands after a push', () => {
        const store = new SystemStatusStore({ fetch: vi.fn(), tab: fakeTab() });
        store.ingest(snapshot({ revision: 5 }));
        store.ingest(snapshot({ revision: 4, overall: { state: 'degraded', cause: 'disconnected', subsystem: 'mqtt' } }));
        expect(store.snapshot?.revision).toBe(5);
        expect(store.snapshot?.overall.state).toBe('ok');
    });

    it('accepts a restarted backend whose count starts again', () => {
        const store = new SystemStatusStore({ fetch: vi.fn(), tab: fakeTab() });
        store.ingest(snapshot({ revision: 40 }));
        store.ingest(snapshot({ revision: 1, startup_instance_id: 'instance-2' }));
        expect(store.snapshot?.startup_instance_id).toBe('instance-2');
    });

    it('tells every subscriber what changed from what', () => {
        const store = new SystemStatusStore({ fetch: vi.fn(), tab: fakeTab() });
        const seen: Array<[number, number | null]> = [];
        const stop = store.subscribe((next, previous) => seen.push([next.revision, previous?.revision ?? null]));
        store.ingest(snapshot({ revision: 1 }));
        store.ingest(snapshot({ revision: 2 }));
        stop();
        store.ingest(snapshot({ revision: 3 }));
        expect(seen).toEqual([[1, null], [2, 1]]);
    });

    it('reads once at start and makes no further request while the stream keeps pushing', async () => {
        vi.useFakeTimers();
        const fetch = vi.fn().mockResolvedValue(snapshot());
        const store = new SystemStatusStore({ fetch, tab: fakeTab() });
        store.start();
        store.setStreamLive(true);
        await pushEvery15s(store, STATUS_FALLBACK_READ_MS * 5);
        expect(fetch).toHaveBeenCalledTimes(1);
        expect(store.stale).toBe(false);
    });

    it('reads once a minute while the stream is down, and stops when it is back', async () => {
        vi.useFakeTimers();
        const fetch = vi.fn().mockResolvedValue(snapshot());
        const store = new SystemStatusStore({ fetch, tab: fakeTab() });
        store.start();
        await vi.advanceTimersByTimeAsync(STATUS_FALLBACK_READ_MS * 2);
        expect(fetch).toHaveBeenCalledTimes(3);
        store.setStreamLive(true);
        await pushEvery15s(store, STATUS_FALLBACK_READ_MS * 3);
        expect(fetch).toHaveBeenCalledTimes(3);
    });

    it('shares one read between callers asking at once and keeps the last reading when a read fails', async () => {
        const fetch = vi.fn().mockResolvedValueOnce(snapshot({ revision: 2 })).mockRejectedValueOnce(new Error('HTTP 502'));
        const store = new SystemStatusStore({ fetch, tab: fakeTab() });
        await Promise.all([store.load(), store.load()]);
        expect(fetch).toHaveBeenCalledTimes(1);
        await store.load();
        expect(store.snapshot?.revision).toBe(2);
    });

    it('marks a live stream that has stopped delivering the status as stale, and reads at once', async () => {
        // A stream can stay open with heartbeats after the server stopped sending it anything.
        vi.useFakeTimers();
        const fetch = vi.fn().mockResolvedValue(snapshot({ revision: 2 }));
        const store = new SystemStatusStore({ fetch, tab: fakeTab() });
        store.start();
        await vi.advanceTimersByTimeAsync(0);
        store.setStreamLive(true);
        store.ingest(snapshot({ revision: 2 }));
        expect(store.stale).toBe(false);
        expect(store.receivedAt).not.toBeNull();

        await vi.advanceTimersByTimeAsync(STATUS_STALE_AFTER_MS - 1);
        expect(store.stale).toBe(false);
        expect(fetch).toHaveBeenCalledTimes(1);

        await vi.advanceTimersByTimeAsync(1);
        expect(fetch).toHaveBeenCalledTimes(2);
        // The read brought a status: it is current again, and the stream is trusted again.
        expect(store.stale).toBe(false);
        await vi.advanceTimersByTimeAsync(STATUS_STALE_AFTER_MS - 1);
        expect(fetch).toHaveBeenCalledTimes(2);
    });

    it('keeps reading once a minute while the status stays stale on a live stream', async () => {
        vi.useFakeTimers();
        const fetch = vi.fn().mockRejectedValue(new Error('HTTP 502'));
        const store = new SystemStatusStore({ fetch, tab: fakeTab() });
        store.start();
        store.setStreamLive(true);
        store.ingest(snapshot());
        await vi.advanceTimersByTimeAsync(STATUS_STALE_AFTER_MS);
        expect(store.stale).toBe(true);
        const afterStale = fetch.mock.calls.length;
        await vi.advanceTimersByTimeAsync(STATUS_FALLBACK_READ_MS * 2);
        expect(fetch.mock.calls.length).toBe(afterStale + 2);
        expect(store.stale).toBe(true);
    });

    it('says it is following only between start and clear', () => {
        const store = new SystemStatusStore({ fetch: vi.fn().mockResolvedValue(snapshot()), tab: fakeTab() });
        expect(store.following).toBe(false);
        store.start();
        expect(store.following).toBe(true);
        store.clear();
        expect(store.following).toBe(false);
    });

    it('forgets everything, and stops reading, when access changes', async () => {
        vi.useFakeTimers();
        const fetch = vi.fn().mockResolvedValue(snapshot());
        const store = new SystemStatusStore({ fetch, tab: fakeTab() });
        store.start();
        await vi.advanceTimersByTimeAsync(0);
        store.clear();
        await vi.advanceTimersByTimeAsync(STATUS_FALLBACK_READ_MS * 3);
        expect(store.snapshot).toBeNull();
        expect(fetch).toHaveBeenCalledTimes(1);
    });
});

describe('status helpers', () => {
    it('finds a subsystem verdict, and nothing before a reading', () => {
        expect(verdictFor(snapshot(), 'frigate')?.cause).toBe('reachable');
        expect(verdictFor(null, 'frigate')).toBeNull();
    });

    it('words a degraded install with the notification causes owners already know', () => {
        const degraded = (cause: string, subsystem: SystemStatus['overall']['subsystem']) =>
            statusNotificationCause(snapshot({ overall: { state: 'degraded', cause, subsystem } }));
        expect(degraded('disconnected', 'mqtt')).toBe('mqtt_down');
        expect(degraded('not_configured', 'mqtt')).toBe('mqtt_not_configured');
        expect(degraded('unreachable', 'frigate')).toBe('frigate_down');
        expect(degraded('pipeline_critical', null)).toBe('pipeline_critical');
        expect(degraded('not_writable', 'storage')).toBe('other');
    });

    it('turns a pushed host sample into the sidebar line sample', () => {
        expect(
            telemetrySampleFrom({
                sampled_at: 1_700_000_000,
                cpu_percent: 12.5,
                accelerator_percent: 40,
                accelerator_kind: 'npu',
                accelerator_label: 'NPU'
            })
        ).toEqual({
            sampled_at: new Date(1_700_000_000_000).toISOString(),
            cpu_percent: 12.5,
            accelerator: { kind: 'npu', label: 'NPU', utilization_percent: 40 }
        });
        expect(telemetrySampleFrom({ sampled_at: 1, cpu_percent: null }).accelerator).toBeNull();
    });

    it('accepts only pushed payloads with every part a reader relies on', () => {
        expect(isSystemStatus(snapshot())).toBe(true);
        expect(isSystemStatus({ revision: 1 })).toBe(false);
        expect(isSystemStatus(null)).toBe(false);
    });
});
