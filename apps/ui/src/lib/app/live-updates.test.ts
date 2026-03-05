import { describe, expect, it } from 'vitest';
import { LiveUpdateCoordinator } from './live-updates';

function buildCoordinator() {
    const calls = {
        upsertRunning: [] as any[],
        markCompleted: [] as any[],
        markFailed: [] as any[]
    };

    const coordinator = new LiveUpdateCoordinator({
        t: (key: string) => key,
        shouldNotify: () => true,
        applyNotificationPolicy: () => true,
        notificationCenter: {
            items: [],
            add: () => undefined,
            upsert: () => undefined,
            remove: () => undefined
        },
        jobProgress: {
            upsertRunning: (input: any) => calls.upsertRunning.push(input),
            markCompleted: (input: any) => calls.markCompleted.push(input),
            markFailed: (input: any) => calls.markFailed.push(input),
            markStale: () => undefined
        },
        detectionsStore: {
            setConnected: () => undefined,
            addDetection: () => undefined,
            updateDetection: () => undefined,
            removeDetection: () => undefined,
            startReclassification: () => undefined,
            updateReclassificationProgress: () => undefined,
            completeReclassification: () => undefined
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
        fetchCacheStats: async () => ({})
    });

    return { coordinator, calls };
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
});
