import { describe, expect, it } from 'vitest';
import type { JobProgressItem } from '../stores/job_progress.svelte';
import type { QueueTelemetryByKind } from './pipeline';
import { buildJobsPipelineModel } from './pipeline';

function runningJob(id: string, kind: string, status: 'running' | 'stale' = 'running'): JobProgressItem {
    const now = 1_000;
    return {
        id,
        kind,
        title: id,
        status,
        current: 1,
        total: 10,
        startedAt: now,
        updatedAt: now,
        source: 'sse'
    };
}

function terminalJob(id: string, kind: string, status: 'completed' | 'failed'): JobProgressItem {
    const now = 2_000;
    return {
        id,
        kind,
        title: id,
        status,
        current: 10,
        total: 10,
        startedAt: 1_000,
        updatedAt: now,
        finishedAt: now,
        source: 'sse'
    };
}

describe('buildJobsPipelineModel', () => {
    it('aggregates queued/running/completed/failed across kinds and marks unknown queue depth', () => {
        const activeJobs: JobProgressItem[] = [
            runningJob('reclassify:evt-1', 'reclassify', 'running'),
            runningJob('reclassify:evt-2', 'reclassify', 'stale'),
            runningJob('backfill:detections:job-1', 'backfill', 'running')
        ];
        const historyJobs: JobProgressItem[] = [
            terminalJob('reclassify:evt-1', 'reclassify', 'completed'),
            terminalJob('backfill:detections:job-1', 'backfill', 'failed')
        ];
        const queueByKind: QueueTelemetryByKind = {
            reclassify: {
                queued: 12,
                running: 2,
                queueDepthKnown: true,
                updatedAt: 3_000
            }
        };

        const model = buildJobsPipelineModel(activeJobs, historyJobs, queueByKind);

        expect(model.lanes.running).toBe(3);
        expect(model.lanes.completed).toBe(1);
        expect(model.lanes.failed).toBe(1);
        expect(model.lanes.queuedKnown).toBe(12);
        expect(model.lanes.queuedUnknownKinds).toBe(0);

        const reclassify = model.kinds.find((k) => k.kind === 'reclassify');
        expect(reclassify).toMatchObject({
            queued: 12,
            queueDepthKnown: true,
            running: 2,
            stale: 1,
            completed: 1,
            failed: 0
        });

        const backfill = model.kinds.find((k) => k.kind === 'backfill');
        expect(backfill).toMatchObject({
            queued: 0,
            queueDepthKnown: true,
            running: 1,
            stale: 0,
            completed: 0,
            failed: 1
        });
    });

    it('keeps queue-only kinds visible even before active jobs appear', () => {
        const model = buildJobsPipelineModel([], [], {
            reclassify: {
                queued: 5,
                running: 0,
                queueDepthKnown: true,
                updatedAt: 8_000
            }
        });

        expect(model.lanes.queuedKnown).toBe(5);
        expect(model.lanes.running).toBe(0);
        expect(model.kinds).toHaveLength(1);
        expect(model.kinds[0]).toMatchObject({
            kind: 'reclassify',
            queued: 5,
            queueDepthKnown: true
        });
    });

    it('hides idle queue-only kinds when queued and running are both zero', () => {
        const model = buildJobsPipelineModel([], [], {
            reclassify: {
                queued: 0,
                running: 0,
                queueDepthKnown: true,
                updatedAt: 9_000
            }
        });

        expect(model.lanes.queuedKnown).toBe(0);
        expect(model.lanes.running).toBe(0);
        expect(model.kinds).toHaveLength(0);
    });

    it('does not count stale reclassify jobs as running when backend reports lower active concurrency', () => {
        const activeJobs: JobProgressItem[] = [
            runningJob('reclassify:evt-1', 'reclassify', 'running'),
            runningJob('reclassify:evt-2', 'reclassify', 'stale'),
            runningJob('reclassify:evt-3', 'reclassify', 'stale')
        ];
        const model = buildJobsPipelineModel(activeJobs, [], {
            reclassify: {
                queued: 6,
                running: 1,
                queueDepthKnown: true,
                updatedAt: 10_000
            }
        });

        expect(model.lanes.running).toBe(1);
        expect(model.kinds[0]).toMatchObject({
            kind: 'reclassify',
            running: 1,
            stale: 2
        });
    });
});
