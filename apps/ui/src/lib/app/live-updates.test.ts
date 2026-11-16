import { describe, expect, it, vi } from 'vitest';
import type { SystemStatus } from '../api/status';
import { LiveUpdateCoordinator, toDetection } from './live-updates';
import { READ_RETRY_MS as WORKSPACE_RETRY_MS } from './retrying-reader';

describe('toDetection', () => {
    it('normalizes required fields at the untrusted SSE boundary', () => {
        expect(toDetection({ frigate_event: 'event-1', display_name: 'Robin' })).toMatchObject({
            frigate_event: 'event-1',
            display_name: 'Robin',
            score: 0,
            detection_time: '',
            camera_name: ''
        });
    });

    it('retains video abstention diagnostics in detection updates', () => {
        const diagnostics = {
            version: 1,
            outcome: 'abstained' as const,
            reason: 'no_source_consensus',
            sampled_frames: 30,
            processed_frames: 30,
            minimum_frame_score: 0.5,
            sources: {}
        };

        expect(toDetection({
            frigate_event: 'event-2',
            video_classification_error: 'video_no_results',
            video_classification_diagnostics: diagnostics
        })).toMatchObject({
            video_classification_error: 'video_no_results',
            video_classification_diagnostics: diagnostics
        });
    });
});

function buildCoordinator(options?: {
    activeJobs?: any[];
    shouldNotify?: boolean;
    hasOwnerAccess?: boolean | (() => boolean);
    refreshOwnerHistory?: () => Promise<void>;
    onGardenHistoryChanged?: () => void;
    onStatus?: (snapshot: unknown) => void;
    syncDiagnosticsWorkspace?: () => Promise<void>;
    onAudioChanged?: () => void;
    onSettingsChanged?: () => void;
}) {
    const calls = {
        upsertRunning: [] as any[],
        markCompleted: [] as any[],
        markFailed: [] as any[],
        markStale: [] as any[],
        remove: [] as any[],
        notificationUpserts: [] as any[],
        notificationRemoves: [] as any[],
        recordError: [] as any[],
        startReclassification: [] as any[],
        updateReclassificationProgress: [] as any[],
        completeReclassification: [] as any[],
        failReclassification: [] as any[],
        markReclassificationStrategyChanged: [] as any[],
        addDetection: [] as unknown[],
        syncDiagnosticsWorkspace: [] as any[]
    };

    const notificationItems: any[] = [];

    const jobProgress = {
        activeJobs: options?.activeJobs ?? ([] as any[]),
        upsertRunning: (input: any) => calls.upsertRunning.push(input),
        markCompleted: (input: any) => calls.markCompleted.push(input),
        markFailed: (input: any) => calls.markFailed.push(input),
        markStale: (maxIdleMs: number) => calls.markStale.push(maxIdleMs),
        remove: (id: string) => calls.remove.push(id)
    };

    const coordinator = new LiveUpdateCoordinator({
        t: (key: string) => key,
        shouldNotify: () => options?.shouldNotify ?? true,
        hasOwnerAccess: typeof options?.hasOwnerAccess === 'function' ? options.hasOwnerAccess : () => (options?.hasOwnerAccess as boolean | undefined) ?? true,
        refreshOwnerHistory: options?.refreshOwnerHistory,
        onGardenHistoryChanged: options?.onGardenHistoryChanged,
        onStatus: options?.onStatus,
        onAudioChanged: options?.onAudioChanged,
        onSettingsChanged: options?.onSettingsChanged,
        applyNotificationPolicy: () => true,
        notificationCenter: {
            items: notificationItems,
            add: (item: any) => {
                notificationItems.unshift(item);
            },
            upsert: (item: any) => {
                calls.notificationUpserts.push(item);
                const idx = notificationItems.findIndex((existing) => existing.id === item.id);
                if (idx >= 0) {
                    notificationItems[idx] = item;
                    return;
                }
                notificationItems.unshift(item);
            },
            remove: (id: string) => {
                calls.notificationRemoves.push(id);
                const idx = notificationItems.findIndex((existing) => existing.id === id);
                if (idx >= 0) {
                    notificationItems.splice(idx, 1);
                }
            }
        },
        jobProgress,
        detectionsStore: {
            setConnected: () => undefined,
            addDetection: (detection) => { calls.addDetection.push(detection); },
            updateDetection: () => undefined,
            removeDetection: () => undefined,
            startReclassification: (...args: any[]) => calls.startReclassification.push(args),
            updateReclassificationProgress: (...args: any[]) => calls.updateReclassificationProgress.push(args),
            completeReclassification: (...args: any[]) => calls.completeReclassification.push(args),
            failReclassification: (...args: any[]) => calls.failReclassification.push(args),
            markReclassificationStrategyChanged: (...args: any[]) => calls.markReclassificationStrategyChanged.push(args)
        },
        settingsStore: {
            liveAnnouncements: false
        },
        announcer: {
            announce: () => undefined
        },
        logger: {
            warn: () => undefined,
            error: () => undefined,
            sseEvent: () => undefined
        },
        diagnostics: {
            recordError: (input: any) => calls.recordError.push(input)
        },
        syncDiagnosticsWorkspace: options?.syncDiagnosticsWorkspace ?? (async () => {
            calls.syncDiagnosticsWorkspace.push(true);
        })
    });

    return { coordinator, calls, notificationItems, jobProgress };
}

function queue(pending: number, active: number): SystemStatus['analysis'] {
    return {
        pending,
        active,
        circuit_open: false,
        open_until: null,
        failure_count: 0,
        pending_capacity: 1000,
        pending_available: 1000 - pending - active
    };
}

function status(overrides: Partial<SystemStatus> & { storage?: 'ok' | 'error' } = {}): SystemStatus {
    const { storage = 'ok', ...rest } = overrides;
    return {
        revision: 1,
        generated_at: '2026-11-16T09:00:00Z',
        startup_instance_id: 'instance-a',
        version: '2.24.0',
        overall: { state: 'ok', cause: 'ok', subsystem: null },
        subsystems: [{ key: 'storage', state: storage, cause: storage === 'ok' ? 'writable' : 'not_writable' }],
        jobs_summary: { running: 0, queued: 0, progress: null },
        jobs: { captured_at: '2026-11-16T09:00:00Z', items: [], lanes: [] },
        analysis: queue(0, 0),
        model: { state: 'ok', cause: 'ready', revision: 'abc' },
        connections: {
            mqtt: { state: 'connected', server: 'mqtt', port: 1883 },
            frigate: { state: 'reachable', url: 'http://frigate:5000' },
            generated_at: '2026-11-16T09:00:00Z'
        },
        diagnostics_revision: 0,
        incident_revision: 'i1',
        health_revision: 'h1',
        ...rest
    };
}

describe('LiveUpdateCoordinator reclassify fallback', () => {
    it('finalizes active reclassify job on detection_updated completed', () => {
        const { coordinator, calls } = buildCoordinator();

        coordinator.handlePayload({
            type: 'reclassification_started',
            data: { event_id: 'evt-1', total_frames: 0, strategy: 'snapshot' }
        });
        coordinator.handlePayload({
            type: 'detection_updated',
            data: {
                frigate_event: 'evt-1',
                video_classification_status: 'completed',
                video_classification_error: null
            }
        });

        expect(calls.markCompleted.length).toBe(1);
        expect(calls.markCompleted[0].id).toBe('reclassify:evt-1');
    });

    it('forwards reclassification_strategy_changed payloads to the detections store', () => {
        const { coordinator, calls } = buildCoordinator();

        coordinator.handlePayload({
            type: 'reclassification_strategy_changed',
            data: {
                event_id: 'evt-1',
                from: 'video',
                to: 'snapshot',
                reason: 'clip_not_retained'
            }
        });

        expect(calls.markReclassificationStrategyChanged.length).toBe(1);
        expect(calls.markReclassificationStrategyChanged[0]).toEqual([
            'evt-1',
            'video',
            'snapshot',
            'clip_not_retained'
        ]);
    });

    it('does not create fallback terminal jobs for unrelated detection updates', () => {
        const { coordinator, calls } = buildCoordinator();

        coordinator.handlePayload({
            type: 'detection_updated',
            data: {
                frigate_event: 'evt-2',
                video_classification_status: 'completed',
                video_classification_error: null
            }
        });

        expect(calls.markCompleted.length).toBe(0);
        expect(calls.markFailed.length).toBe(0);
    });

    it('marks tracked reclassify jobs as failed from detection_updated fallback', () => {
        const { coordinator, calls } = buildCoordinator();

        coordinator.handlePayload({
            type: 'reclassification_started',
            data: { event_id: 'evt-3', total_frames: 0, strategy: 'snapshot' }
        });
        coordinator.handlePayload({
            type: 'detection_updated',
            data: {
                frigate_event: 'evt-3',
                video_classification_status: 'failed',
                video_classification_error: 'video_timeout'
            }
        });

        expect(calls.markFailed.length).toBe(1);
        expect(calls.markFailed[0].id).toBe('reclassify:evt-3');
    });

    it('does not create additional running updates from pending fallback status', () => {
        const { coordinator, calls } = buildCoordinator();

        coordinator.handlePayload({
            type: 'reclassification_started',
            data: { event_id: 'evt-4', total_frames: 0, strategy: 'manual' }
        });
        expect(calls.upsertRunning.length).toBe(1);

        coordinator.handlePayload({
            type: 'detection_updated',
            data: {
                frigate_event: 'evt-4',
                video_classification_status: 'pending',
                video_classification_error: null
            }
        });

        // Keep the originally started job, but do not duplicate/revive it from pending fallback.
        expect(calls.upsertRunning.length).toBe(1);
    });

    it('preserves category_name from detection_updated payloads', () => {
        const updates: any[] = [];
        const coordinator = new LiveUpdateCoordinator({
            t: (key: string) => key,
            shouldNotify: () => false,
            hasOwnerAccess: () => true,
            applyNotificationPolicy: () => true,
            notificationCenter: { items: [], add: () => undefined, upsert: () => undefined, remove: () => undefined },
            jobProgress: { activeJobs: [], upsertRunning: () => undefined, markCompleted: () => undefined, markFailed: () => undefined, markStale: () => undefined, remove: () => undefined },
            detectionsStore: {
                setConnected: () => undefined,
                addDetection: () => undefined,
                updateDetection: (detection: any) => updates.push(detection),
                removeDetection: () => undefined,
                startReclassification: () => undefined,
                updateReclassificationProgress: () => undefined,
                completeReclassification: () => undefined,
                failReclassification: () => undefined,
                markReclassificationStrategyChanged: () => undefined
            },
            settingsStore: { liveAnnouncements: false },
            announcer: { announce: () => undefined },
            logger: { warn: () => undefined, error: () => undefined, sseEvent: () => undefined },
            diagnostics: { recordError: () => undefined }
        });

        coordinator.handlePayload({
            type: 'detection_updated',
            data: {
                frigate_event: 'evt-category',
                display_name: 'Blue Jay',
                category_name: 'blue jay',
                score: 0.9,
                timestamp: '2026-03-26T12:00:00Z',
                camera: 'BirdCam',
                is_hidden: false,
                is_favorite: false,
                manual_tagged: true,
                video_classification_status: 'completed',
                video_classification_label: 'blue jay'
            }
        });

        expect(updates).toHaveLength(1);
        expect(updates[0].category_name).toBe('blue jay');
    });

    it('warns the owner only when the media folder cannot be written, and clears the retired cache notice', () => {
        const unwritable = buildCoordinator();
        unwritable.notificationItems.push({ id: 'system:cache-disabled:old-start' });
        unwritable.coordinator.applySystemStatus(status({ storage: 'error' }), null);
        const ids = unwritable.notificationItems.map((item) => String(item.id));
        expect(ids.some((id) => id.startsWith('system:media-storage-unavailable:'))).toBe(true);
        expect(ids.some((id) => id.startsWith('system:cache-disabled'))).toBe(false);

        const writable = buildCoordinator();
        writable.coordinator.applySystemStatus(status(), null);
        expect(writable.notificationItems.some((item) => String(item.id).startsWith('system:media-storage-unavailable'))).toBe(false);
    });

    it('says why health is not ok instead of the backend word, and follows a change of cause', () => {
        const { coordinator, notificationItems } = buildCoordinator();
        const first = status({ overall: { state: 'degraded', cause: 'disconnected', subsystem: 'mqtt' } });
        coordinator.applySystemStatus(first, null);
        let health = notificationItems.filter((item) => String(item.id).startsWith('system:health'));
        expect(health).toHaveLength(1);
        expect(health[0].message).toBe('notifications.system_health_cause.mqtt_down');
        expect(health[0].message).not.toContain('degraded');

        const second = status({ revision: 2, overall: { state: 'degraded', cause: 'unreachable', subsystem: 'frigate' } });
        coordinator.applySystemStatus(second, first);
        health = notificationItems.filter((item) => String(item.id).startsWith('system:health'));
        expect(health).toHaveLength(1);
        expect(health[0].message).toBe('notifications.system_health_cause.frigate_down');

        coordinator.applySystemStatus(status({ revision: 3 }), second);
        expect(notificationItems.some((item) => String(item.id).startsWith('system:health'))).toBe(false);
    });

    it('reads the incident workspace on the first status and when the server records a new fault, not on every push', async () => {
        const { coordinator, calls } = buildCoordinator();
        const first = status();
        coordinator.applySystemStatus(first, null);
        await vi.waitFor(() => expect(calls.syncDiagnosticsWorkspace).toHaveLength(1));
        const figures = status({ generated_at: '2026-11-16T09:00:15Z' });
        coordinator.applySystemStatus(figures, first);
        await Promise.resolve();
        expect(calls.syncDiagnosticsWorkspace).toHaveLength(1);
        coordinator.applySystemStatus(status({ revision: 2, diagnostics_revision: 4 }), figures);
        await vi.waitFor(() => expect(calls.syncDiagnosticsWorkspace).toHaveLength(2));
    });

    it('reads the incident workspace again when a verdict changes, so a recovery closes its incident', async () => {
        const { coordinator, calls } = buildCoordinator();
        const onCpu = status({ incident_revision: 'finder-cpu', subsystems: [{ key: 'finder', state: 'degraded', cause: 'cpu_fallback' }] });
        coordinator.applySystemStatus(onCpu, null);
        // The finder is back on its accelerator; no new fault was recorded for that.
        coordinator.applySystemStatus(status({ revision: 2, incident_revision: 'finder-ok', subsystems: [{ key: 'finder', state: 'ok', cause: 'ready' }] }), onCpu);
        await vi.waitFor(() => expect(calls.syncDiagnosticsWorkspace).toHaveLength(2));
    });

    it('retries a failed workspace read with a growing wait until one succeeds', async () => {
        vi.useFakeTimers();
        try {
            const sync = vi.fn<() => Promise<void>>()
                .mockRejectedValueOnce(new Error('HTTP 502'))
                .mockRejectedValueOnce(new Error('HTTP 502'))
                .mockResolvedValue(undefined);
            const { coordinator } = buildCoordinator({ syncDiagnosticsWorkspace: sync });
            coordinator.applySystemStatus(status(), null);
            await vi.advanceTimersByTimeAsync(0);
            expect(sync).toHaveBeenCalledTimes(1);
            await vi.advanceTimersByTimeAsync(WORKSPACE_RETRY_MS[0]);
            expect(sync).toHaveBeenCalledTimes(2);
            await vi.advanceTimersByTimeAsync(WORKSPACE_RETRY_MS[0]);
            expect(sync).toHaveBeenCalledTimes(2);
            await vi.advanceTimersByTimeAsync(WORKSPACE_RETRY_MS[1] - WORKSPACE_RETRY_MS[0]);
            expect(sync).toHaveBeenCalledTimes(3);
            await vi.advanceTimersByTimeAsync(10 * WORKSPACE_RETRY_MS[WORKSPACE_RETRY_MS.length - 1]);
            expect(sync).toHaveBeenCalledTimes(3);
        } finally {
            vi.useRealTimers();
        }
    });

    it('reads the incident workspace again when a video breaker closes, though nothing else changed', async () => {
        const { coordinator, calls } = buildCoordinator();
        const tripped = status({ incident_revision: 'breaker-open' });
        coordinator.applySystemStatus(tripped, null);
        coordinator.applySystemStatus(status({ revision: 2, incident_revision: 'breaker-closed' }), tripped);
        await vi.waitFor(() => expect(calls.syncDiagnosticsWorkspace).toHaveLength(2));
    });

    it('stops retrying the workspace once owner access is gone, and after an access change', async () => {
        vi.useFakeTimers();
        try {
            let owner = true;
            const sync = vi.fn<() => Promise<void>>().mockRejectedValue(new Error('HTTP 502'));
            const { coordinator } = buildCoordinator({ syncDiagnosticsWorkspace: sync, hasOwnerAccess: () => owner });
            coordinator.applySystemStatus(status(), null);
            await vi.advanceTimersByTimeAsync(0);
            owner = false;
            await vi.advanceTimersByTimeAsync(10 * WORKSPACE_RETRY_MS[WORKSPACE_RETRY_MS.length - 1]);
            expect(sync).toHaveBeenCalledTimes(1);

            owner = true;
            coordinator.applySystemStatus(status({ revision: 2, diagnostics_revision: 3 }), status());
            await vi.advanceTimersByTimeAsync(0);
            expect(sync).toHaveBeenCalledTimes(2);
            coordinator.resetForAccessChange();
            await vi.advanceTimersByTimeAsync(10 * WORKSPACE_RETRY_MS[WORKSPACE_RETRY_MS.length - 1]);
            expect(sync).toHaveBeenCalledTimes(2);
        } finally {
            vi.useRealTimers();
        }
    });

    it('ignores a workspace read that fails after the access it was made for has gone', async () => {
        vi.useFakeTimers();
        try {
            let fail: (error: Error) => void = () => undefined;
            const sync = vi.fn<() => Promise<void>>()
                .mockImplementationOnce(() => new Promise((_resolve, reject) => { fail = reject; }))
                .mockResolvedValue(undefined);
            const { coordinator } = buildCoordinator({ syncDiagnosticsWorkspace: sync });
            coordinator.applySystemStatus(status(), null);
            coordinator.resetForAccessChange();
            fail(new Error('HTTP 502'));
            await vi.advanceTimersByTimeAsync(10 * WORKSPACE_RETRY_MS[WORKSPACE_RETRY_MS.length - 1]);
            expect(sync).toHaveBeenCalledTimes(1);
        } finally {
            vi.useRealTimers();
        }
    });

    it('refreshes stale owner history when the status changes, even when notifications are off', () => {
        const refreshOwnerHistory = vi.fn(async () => undefined);
        const { coordinator } = buildCoordinator({ refreshOwnerHistory, shouldNotify: false });
        const first = status();
        coordinator.applySystemStatus(first, null);
        coordinator.applySystemStatus(status(), first);
        expect(refreshOwnerHistory).toHaveBeenCalledOnce();
        coordinator.applySystemStatus(status({ revision: 2 }), first);
        expect(refreshOwnerHistory).toHaveBeenCalledTimes(2);
    });

    it('does nothing with a status for a guest', () => {
        const refreshOwnerHistory = vi.fn(async () => undefined);
        const { coordinator, calls } = buildCoordinator({ refreshOwnerHistory, hasOwnerAccess: false });
        coordinator.applySystemStatus(status({ overall: { state: 'degraded', cause: 'disconnected', subsystem: 'mqtt' } }), null);
        expect(refreshOwnerHistory).not.toHaveBeenCalled();
        expect(calls.syncDiagnosticsWorkspace).toEqual([]);
    });

    it('clears synthetic batch analysis state when the backend instance changes', () => {
        const { coordinator, calls, notificationItems } = buildCoordinator();
        const busy = status({ analysis: queue(8, 1) });
        coordinator.applySystemStatus(busy, null);
        expect(notificationItems.some((item) => item.id === 'reclassify:progress')).toBe(true);
        expect(calls.remove).toEqual([]);
        expect(calls.notificationRemoves).toEqual([]);

        coordinator.applySystemStatus(status({ startup_instance_id: 'instance-b', analysis: queue(8, 1) }), busy);

        expect(calls.remove).toContain('reclassify:progress');
        expect(calls.notificationRemoves).toContain('reclassify:progress');
    });

    it('does not remove per-event reclassify jobs when clearing synthetic batch state after restart', () => {
        const { coordinator, calls } = buildCoordinator({
            activeJobs: [{ id: 'reclassify:evt-1', kind: 'reclassify', status: 'running' }]
        });
        const busy = status({ analysis: queue(3, 1) });
        coordinator.applySystemStatus(busy, null);
        coordinator.applySystemStatus(status({ startup_instance_id: 'instance-b', analysis: queue(3, 1) }), busy);

        expect(calls.remove).toContain('reclassify:progress');
        expect(calls.remove).not.toContain('reclassify:evt-1');
    });

    it('preserves per-event reclassify progress notifications when clearing synthetic batch state after restart', () => {
        const { coordinator, calls, notificationItems } = buildCoordinator();
        notificationItems.push({
            id: 'reclassify:progress:evt-1',
            type: 'process',
            title: 'Event reclassify',
            message: '1 / 3',
            timestamp: Date.now(),
            read: false,
            meta: { source: 'sse', event_id: 'evt-1' }
        });
        const busy = status({ analysis: queue(2, 1) });
        coordinator.applySystemStatus(busy, null);
        coordinator.applySystemStatus(status({ startup_instance_id: 'instance-b', analysis: queue(2, 1) }), busy);

        expect(calls.notificationRemoves).toContain('reclassify:progress');
        expect(calls.notificationRemoves).not.toContain('reclassify:progress:evt-1');
        expect(notificationItems.some((item) => item.id === 'reclassify:progress:evt-1')).toBe(true);
    });

    it('creates a synthetic batch analysis job when queue status shows work but no event jobs are active', () => {
        const { coordinator, calls } = buildCoordinator();

        coordinator.applySystemStatus(status({ analysis: queue(6, 1) }), null);

        expect(calls.upsertRunning.length).toBe(1);
        expect(calls.upsertRunning[0].id).toBe('reclassify:progress');
        expect(calls.upsertRunning[0].kind).toBe('reclassify_batch');
        expect(calls.upsertRunning[0].total).toBe(7);
        expect(calls.notificationUpserts.length).toBe(1);
        expect(calls.notificationUpserts[0].id).toBe('reclassify:progress');
        expect(calls.notificationUpserts[0].type).toBe('process');
        expect(calls.notificationUpserts[0].meta?.source).toBe('poll');
    });

    it('settles synthetic batch UI when queue status reports idle', () => {
        const { coordinator, calls } = buildCoordinator();
        const busy = status({ analysis: queue(4, 1) });
        const idle = status({ revision: 2, analysis: queue(0, 0) });

        coordinator.applySystemStatus(busy, null);
        coordinator.applySystemStatus(idle, busy);
        coordinator.applySystemStatus(status({ revision: 3, analysis: queue(0, 0) }), idle);

        expect(calls.markCompleted.length).toBe(1);
        expect(calls.markCompleted[0].id).toBe('reclassify:progress');
        const terminalNotification = calls.notificationUpserts[calls.notificationUpserts.length - 1];
        expect(terminalNotification.id).toBe('reclassify:progress');
        expect(terminalNotification.type).toBe('update');
        expect(terminalNotification.read).toBe(true);
    });

    it('does not add a synthetic batch job when per-event reclassify jobs are already active', () => {
        const { coordinator, calls } = buildCoordinator({
            activeJobs: [{ id: 'reclassify:evt-1', kind: 'reclassify', status: 'running' }]
        });

        coordinator.applySystemStatus(status({ analysis: queue(2, 1) }), null);

        expect(calls.upsertRunning.length).toBe(0);
        expect(calls.notificationUpserts.length).toBe(1);
        expect(calls.remove).toContain('reclassify:progress');
    });

    it('does not track reclassification jobs for guest/public sessions', () => {
        const { coordinator, calls } = buildCoordinator({ shouldNotify: false });

        coordinator.handlePayload({
            type: 'reclassification_started',
            data: { event_id: 'evt-guest', total_frames: 12, strategy: 'snapshot' }
        });
        coordinator.handlePayload({
            type: 'reclassification_progress',
            data: {
                event_id: 'evt-guest',
                current_frame: 4,
                total_frames: 12,
                frame_score: 0.9,
                top_label: 'Blue Tit'
            }
        });
        coordinator.handlePayload({
            type: 'reclassification_completed',
            data: {
                event_id: 'evt-guest',
                results: [{ label: 'Blue Tit', score: 0.9 }]
            }
        });

        expect(calls.upsertRunning.length).toBe(0);
        expect(calls.markCompleted.length).toBe(0);
        expect(calls.markFailed.length).toBe(0);
        expect(calls.notificationUpserts.length).toBe(0);
        expect(calls.startReclassification.length).toBe(0);
        expect(calls.updateReclassificationProgress.length).toBe(0);
        expect(calls.completeReclassification.length).toBe(1);
    });

    it('settles a no-result reclassification without reporting a failure', () => {
        const { coordinator, calls } = buildCoordinator();

        coordinator.handlePayload({
            type: 'reclassification_started',
            data: { event_id: 'evt-no-result', total_frames: 12, strategy: 'video' }
        });
        coordinator.handlePayload({
            type: 'reclassification_strategy_changed',
            data: { event_id: 'evt-no-result', from: 'video', to: 'snapshot', reason: 'video_no_results' }
        });
        coordinator.handlePayload({
            type: 'detection_updated',
            data: {
                frigate_event: 'evt-no-result',
                video_classification_status: 'failed',
                video_classification_error: 'video_no_results'
            }
        });
        coordinator.handlePayload({
            type: 'reclassification_completed',
            data: {
                event_id: 'evt-no-result',
                results: [],
                outcome: 'no_result',
                reason: 'video_no_results',
                diagnostics: {
                    version: 1,
                    outcome: 'abstained',
                    reason: 'no_source_consensus',
                    sampled_frames: 30,
                    processed_frames: 30,
                    minimum_frame_score: 0.5,
                    sources: {}
                }
            }
        });

        expect(calls.markCompleted).toHaveLength(1);
        expect(calls.markCompleted[0].message).toBe('notifications.reclassify_no_result');
        expect(calls.markFailed).toHaveLength(0);
        expect(calls.completeReclassification).toEqual([[
            'evt-no-result',
            [],
            'no_result',
            'video_no_results',
            expect.objectContaining({ reason: 'no_source_consensus' })
        ]]);
        expect(calls.notificationUpserts.at(-1)?.message).toBe('notifications.reclassify_no_result');
    });

    it('treats an empty legacy completion as no result instead of generic success', () => {
        const { coordinator, calls } = buildCoordinator();

        coordinator.handlePayload({
            type: 'reclassification_started',
            data: { event_id: 'evt-legacy-empty', total_frames: 12, strategy: 'video' }
        });
        coordinator.handlePayload({
            type: 'reclassification_completed',
            data: { event_id: 'evt-legacy-empty', results: [] }
        });

        expect(calls.completeReclassification).toEqual([
            ['evt-legacy-empty', [], 'no_result', null, null]
        ]);
        expect(calls.markCompleted[0].message).toBe('notifications.reclassify_no_result');
    });

    it('keeps a terminal technical failure visible with its reason', () => {
        const { coordinator, calls } = buildCoordinator();

        coordinator.handlePayload({
            type: 'reclassification_started',
            data: { event_id: 'evt-terminal-failure', total_frames: 12, strategy: 'video' }
        });
        coordinator.handlePayload({
            type: 'reclassification_completed',
            data: {
                event_id: 'evt-terminal-failure',
                results: [],
                outcome: 'failed',
                reason: 'video_timeout'
            }
        });

        expect(calls.markFailed).toHaveLength(1);
        expect(calls.markCompleted).toHaveLength(0);
        expect(calls.completeReclassification).toEqual([
            ['evt-terminal-failure', [], 'failed', 'video_timeout', null]
        ]);
        expect(calls.failReclassification).toHaveLength(0);
    });

    it('settles an explicit reclassification failure and dismisses its overlay', () => {
        const { coordinator, calls } = buildCoordinator();

        coordinator.handlePayload({
            type: 'reclassification_started',
            data: { event_id: 'evt-failed', total_frames: 12, strategy: 'video' }
        });
        coordinator.handlePayload({
            type: 'reclassification_failed',
            data: { event_id: 'evt-failed', error: 'snapshot unavailable' }
        });

        expect(calls.markFailed).toHaveLength(1);
        expect(calls.failReclassification).toEqual([['evt-failed']]);
        expect(calls.completeReclassification).toHaveLength(0);
    });

    it('settles orphaned process notifications when no active jobs back them', () => {
        const { coordinator, calls, notificationItems } = buildCoordinator();
        notificationItems.push({
            id: 'reclassify:progress',
            type: 'process',
            title: 'Batch analysis',
            message: 'running',
            timestamp: Date.now() - (5 * 60 * 1000),
            read: false,
            meta: { source: 'sse' }
        });

        coordinator.pruneStaleProcessNotifications();

        expect(calls.notificationUpserts.length).toBe(1);
        expect(calls.notificationUpserts[0].id).toBe('reclassify:progress');
        expect(calls.notificationUpserts[0].type).toBe('update');
        expect(calls.notificationUpserts[0].read).toBe(true);
        expect(calls.notificationUpserts[0].meta?.stale).toBe(true);
    });

    it('keeps process notifications when a matching active job exists', () => {
        const { coordinator, calls, notificationItems } = buildCoordinator({
            activeJobs: [
                {
                    id: 'reclassify:evt-1',
                    kind: 'reclassify',
                    status: 'running'
                }
            ]
        });
        notificationItems.push({
            id: 'reclassify:progress',
            type: 'process',
            title: 'Batch analysis',
            message: 'running',
            timestamp: Date.now() - (5 * 60 * 1000),
            read: false,
            meta: { source: 'sse' }
        });

        coordinator.pruneStaleProcessNotifications();

        expect(calls.notificationUpserts.length).toBe(0);
    });

    it('keeps backfill progress totals unknown when the backend has not reported one yet', () => {
        const { coordinator, calls } = buildCoordinator();

        coordinator.handlePayload({
            type: 'backfill_started',
            data: {
                id: 'job-unknown-total',
                kind: 'detections',
                status: 'running',
                processed: 0,
                total: 0,
                new_detections: 0,
                skipped: 0,
                errors: 0,
                message: 'Scanning historical events'
            }
        });

        expect(calls.upsertRunning.length).toBe(1);
        expect(calls.upsertRunning[0].total).toBe(0);
        expect(calls.upsertRunning[0].message).toBe('Scanning historical events');
    });
});

it('keeps current and initial classification input in owner live updates', () => {
    const current = { source: 'owner_species_choice' };
    const original = { source: 'full_frame', is_cropped: false };
    const result = toDetection({ frigate_event: 'source-change', classification_input: current, initial_classification_input: original });
    expect(result.classification_input).toEqual(current);
    expect(result.initial_classification_input).toEqual(original);
});


describe('private Garden live updates', () => {
    it.each([true, false])('invalidates Garden only with owner access (%s), without bird or notification changes', (owner) => {
        const onGardenHistoryChanged = vi.fn();
        const { coordinator, calls } = buildCoordinator({ hasOwnerAccess: owner, shouldNotify: false, onGardenHistoryChanged });
        coordinator.handlePayload({ type: 'garden_history_changed' });
        expect(onGardenHistoryChanged).toHaveBeenCalledTimes(owner ? 1 : 0);
        expect(calls.addDetection).toEqual([]);
        expect(calls.notificationUpserts).toEqual([]);
    });

    it.each([
        ['audio_detected', true], ['audio_detected', false],
        ['audio_history_changed', true], ['audio_history_changed', false]
    ])('passes on %s, a new call or a hidden or restored one, only with owner access (%s)', (type, owner) => {
        const onAudioChanged = vi.fn();
        const { coordinator, calls } = buildCoordinator({ hasOwnerAccess: owner, shouldNotify: false, onAudioChanged });
        coordinator.handlePayload({ type });
        expect(onAudioChanged).toHaveBeenCalledTimes(owner ? 1 : 0);
        expect(calls.notificationUpserts).toEqual([]);
    });

    it('says the settings changed, so shared readings that depend on them are read again', () => {
        const onSettingsChanged = vi.fn();
        const { coordinator } = buildCoordinator({ shouldNotify: false, onSettingsChanged });
        coordinator.handlePayload({ type: 'settings_updated', data: { changed_fields: ['inference_provider'] } });
        expect(onSettingsChanged).toHaveBeenCalledTimes(1);
    });

    it('leaves a connection change to the status push that follows it', () => {
        const { coordinator, calls } = buildCoordinator({ shouldNotify: false });
        coordinator.handlePayload({ type: 'service_connections_changed' });
        expect(calls.notificationUpserts).toEqual([]);
        expect(calls.recordError).toEqual([]);
    });

    it.each([true, false])('hands a pushed status to the owner only (%s)', (owner) => {
        const onStatus = vi.fn();
        const { coordinator } = buildCoordinator({ hasOwnerAccess: owner, onStatus });
        coordinator.handlePayload({ type: 'status', data: { revision: 1 } });
        expect(onStatus).toHaveBeenCalledTimes(owner ? 1 : 0);
        if (owner) expect(onStatus).toHaveBeenCalledWith({ revision: 1 });
    });
});
