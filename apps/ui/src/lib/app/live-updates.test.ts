import { describe, expect, it } from 'vitest';
import { LiveUpdateCoordinator } from './live-updates';

function buildCoordinator(options?: { activeJobs?: any[]; shouldNotify?: boolean }) {
    const calls = {
        upsertRunning: [] as any[],
        markCompleted: [] as any[],
        markFailed: [] as any[],
        markStale: [] as any[],
        notificationUpserts: [] as any[],
        ingestHealth: [] as any[],
        recordError: [] as any[],
        startReclassification: [] as any[],
        updateReclassificationProgress: [] as any[],
        completeReclassification: [] as any[]
    };

    const notificationItems: any[] = [];

    const jobProgress = {
        activeJobs: options?.activeJobs ?? ([] as any[]),
        upsertRunning: (input: any) => calls.upsertRunning.push(input),
        markCompleted: (input: any) => calls.markCompleted.push(input),
        markFailed: (input: any) => calls.markFailed.push(input),
        markStale: (maxIdleMs: number) => calls.markStale.push(maxIdleMs)
    };

    const coordinator = new LiveUpdateCoordinator({
        t: (key: string) => key,
        shouldNotify: () => options?.shouldNotify ?? true,
        applyNotificationPolicy: () => true,
        notificationCenter: {
            items: notificationItems,
            add: () => undefined,
            upsert: (item: any) => {
                calls.notificationUpserts.push(item);
                const idx = notificationItems.findIndex((existing) => existing.id === item.id);
                if (idx >= 0) {
                    notificationItems[idx] = item;
                    return;
                }
                notificationItems.unshift(item);
            },
            remove: () => undefined
        },
        jobProgress,
        detectionsStore: {
            setConnected: () => undefined,
            addDetection: () => undefined,
            updateDetection: () => undefined,
            removeDetection: () => undefined,
            startReclassification: (...args: any[]) => calls.startReclassification.push(args),
            updateReclassificationProgress: (...args: any[]) => calls.updateReclassificationProgress.push(args),
            completeReclassification: (...args: any[]) => calls.completeReclassification.push(args)
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
        checkHealth: async () => ({}),
        fetchCacheStats: async () => ({}),
        diagnostics: {
            ingestHealth: (health: any) => calls.ingestHealth.push(health),
            recordError: (input: any) => calls.recordError.push(input)
        }
    });

    return { coordinator, calls, notificationItems, jobProgress };
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
            data: { event_id: 'evt-4', total_frames: 0, strategy: 'auto_video' }
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

    it('forwards health payloads to diagnostics ingest', async () => {
        const { coordinator, calls } = buildCoordinator();
        await coordinator.runOwnerSystemChecks();
        expect(calls.ingestHealth.length).toBe(1);
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
