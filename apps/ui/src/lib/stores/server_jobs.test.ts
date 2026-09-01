import { beforeAll, describe, expect, it } from 'vitest';
import { addMessages, init, locale } from 'svelte-i18n';
import en from '../i18n/locales/en.json';
import { ServerJobsStore } from './server_jobs.svelte';

describe('ServerJobsStore', () => {
    it('names background work by what it is, not by a Frigate event id', () => {
        // The jobs view listed rows titled "1788274081.133679-ycxd6p". An identifier does not
        // tell an owner whether the row matters; the kind of work does.
        addMessages('en', en);
        init({ fallbackLocale: 'en', initialLocale: 'en' });
        locale.set('en');

        const store = new ServerJobsStore();
        store.snapshot = {
            captured_at: '2026-07-22T12:00:00Z',
            items: [{
                id: 'video:1788274081.133679-ycxd6p',
                event_id: '1788274081.133679-ycxd6p',
                kind: 'auto_video',
                source: 'maintenance',
                status: 'running',
                phase: 'analyzing',
                current: 3,
                total: 15,
                unit: 'frames',
                visibility: 'routine'
            }],
            lanes: []
        };

        expect(store.activeJobs[0].title).toBe('Automatic video analysis');
        expect(store.activeJobs[0].title).not.toContain('1788274081');
        // Two clips analysed at once would otherwise be two identical rows, so the event
        // stays visible as detail rather than disappearing with the id.
        expect(store.activeJobs[0].message).toBe('analyzing \u00b7 1788274081.133679-ycxd6p');
    });

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

    it('keeps server identity without rolling back fresher browser progress', () => {
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
        expect(merged[0]).toMatchObject({ current: 2, total: 15, startedAt: 1 });
        expect(merged[0].updatedAt).toBeGreaterThanOrEqual(2);
    });

    it('keeps a missing server timestamp and progress monotonic across polls', () => {
        const store = new ServerJobsStore();
        store.snapshot = {
            captured_at: '2026-07-22T12:00:00Z',
            items: [{
                id: 'full_visit:evt-3', event_id: 'evt-3', kind: 'full_visit', source: 'automatic',
                status: 'running', phase: 'fetching_media', current: 4, total: 10, unit: 'items'
            }],
            lanes: []
        };
        const first = store.activeJobs[0];

        store.snapshot = {
            captured_at: '2026-07-22T12:00:05Z',
            items: [{
                id: 'full_visit:evt-3', event_id: 'evt-3', kind: 'full_visit', source: 'automatic',
                status: 'running', phase: 'fetching_media', current: 2, total: 10, unit: 'items'
            }],
            lanes: []
        };
        const second = store.activeJobs[0];

        expect(second.startedAt).toBe(first.startedAt);
        expect(second.current).toBe(4);
        expect(second.updatedAt).toBeGreaterThanOrEqual(first.updatedAt);
    });
});
