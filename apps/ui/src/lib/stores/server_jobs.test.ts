import { describe, expect, it } from 'vitest';
import { ServerJobsStore } from './server_jobs.svelte';

describe('ServerJobsStore', () => {
    it('keeps queued server work distinct from running worker use', () => {
        const store = new ServerJobsStore();
        store.snapshot = {
            captured_at: '2026-07-22T12:00:00Z',
            items: [{
                id: 'video:evt-1',
                event_id: 'evt-1',
                kind: 'video_analysis',
                source: 'maintenance',
                status: 'queued',
                phase: 'waiting',
                current: 0,
                total: 15,
                unit: 'frames',
                visibility: 'prominent'
            }],
            lanes: [{
                kind: 'video_analysis',
                queued: 1,
                running: 0,
                completed: 0,
                failed: 0,
                capacity: 1000,
                max_concurrent_configured: 2,
                max_concurrent_effective: 1,
                state: 'queued'
            }]
        };

        expect(store.activeJobs[0]).toMatchObject({ status: 'queued', current: 0, total: 15 });
        expect(store.queueByKind.video_analysis).toMatchObject({
            queued: 1,
            running: 0,
            maxConcurrentConfigured: 2,
            maxConcurrentEffective: 1
        });
    });

    it('prefers server truth over a browser-local job for the same event', () => {
        const store = new ServerJobsStore();
        store.snapshot = {
            captured_at: '2026-07-22T12:00:00Z',
            items: [{
                id: 'video:evt-2',
                event_id: 'evt-2',
                kind: 'video_analysis',
                source: 'maintenance',
                status: 'running',
                phase: 'analyzing',
                current: 0,
                total: 15,
                unit: 'frames',
                visibility: 'prominent'
            }],
            lanes: []
        };

        const merged = store.mergeActive([{
            id: 'reclassify:evt-2',
            kind: 'reclassify',
            title: 'Local duplicate',
            status: 'running',
            current: 2,
            total: 15,
            startedAt: 1,
            updatedAt: 2,
            source: 'sse'
        }]);

        expect(merged).toHaveLength(1);
        expect(merged[0].id).toBe('video:evt-2');
    });
});
