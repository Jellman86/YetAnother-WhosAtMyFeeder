import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import type { NotificationItem } from '../stores/notification_center.svelte';
import type { JobProgressItem } from '../stores/job_progress.svelte';
import {
    buildTimelineItems,
    countByFilter,
    filterNotifications,
    groupNotifications,
    isOwnerOnlyFilter,
    progressOf,
    toneOf
} from './notification-timeline';

const NOW = new Date('2026-08-13T14:00:00').getTime();

function item(over: Partial<NotificationItem> & { id: string }): NotificationItem {
    return {
        type: 'detection',
        title: 'x',
        timestamp: NOW,
        read: false,
        ...over
    } as NotificationItem;
}

function job(over: Partial<JobProgressItem> & { id: string }): JobProgressItem {
    return {
        kind: 'reclassify',
        title: 'Reclassification',
        status: 'running',
        current: 1,
        total: 2,
        startedAt: NOW - 1000,
        updatedAt: NOW,
        source: 'sse',
        ...over
    };
}

describe('notification timeline', () => {
    beforeAll(() => {
        vi.stubEnv('TZ', 'Europe/London');
    });

    afterAll(() => {
        vi.unstubAllEnvs();
    });

    it('reserves amber for the things that need a person', () => {
        // layout-patterns 1.3: a running job needs nobody, so it must not claim the attention colour.
        expect(toneOf(item({ id: 'a', type: 'process', meta: { kind: 'error' } }))).toBe('attention');
        expect(toneOf(item({ id: 'b', type: 'process', meta: { current: 5, total: 10 } }))).toBe('running');
        expect(toneOf(item({ id: 'c', type: 'process', meta: { current: 10, total: 10 } }))).toBe('done');
        expect(toneOf(item({ id: 'd', type: 'update' }))).toBe('info');
        expect(toneOf(item({ id: 'e', type: 'detection' }))).toBe('info');
    });

    it('files a failed job under errors whatever its type says', () => {
        const failed = item({ id: 'f', type: 'process', meta: { kind: 'failed' } });
        expect(filterNotifications([failed], 'errors')).toHaveLength(1);
        expect(filterNotifications([failed], 'jobs')).toHaveLength(0);
    });

    it('includes real job-store failures and merges their matching notification row', () => {
        const notifications = [
            item({
                id: 'backfill:detections:42',
                type: 'update',
                title: 'Backfill failed',
                message: 'Classifier unavailable',
                meta: { kind: 'detections', current: 4, total: 10 }
            })
        ];
        const jobs = [
            job({
                id: 'backfill:detections:42',
                status: 'failed',
                current: 4,
                total: 10,
                finishedAt: NOW
            })
        ];

        const timeline = buildTimelineItems(notifications, jobs);

        expect(timeline).toHaveLength(1);
        expect(timeline[0].title).toBe('Backfill failed');
        expect(timeline[0].message).toBe('Classifier unavailable');
        expect(timeline[0].meta?.status).toBe('failed');
        expect(filterNotifications(timeline, 'errors')).toHaveLength(1);
        expect(toneOf(timeline[0])).toBe('attention');
    });

    it('uses jobs as the source of process rows without duplicating progress notifications', () => {
        const notifications = [
            item({
                id: 'reclassify:progress:event-7',
                type: 'process',
                title: 'Reclassifying',
                meta: { current: 3, total: 8 }
            })
        ];
        const jobs = [job({ id: 'reclassify:event-7', current: 3, total: 8 })];

        const timeline = buildTimelineItems(notifications, jobs);

        expect(timeline).toHaveLength(1);
        expect(timeline[0].id).toBe('reclassify:progress:event-7');
        expect(timeline[0].meta?.status).toBe('running');
        expect(filterNotifications(timeline, 'jobs')).toHaveLength(1);
    });

    it('deduplicates the same job reported by local and server sources', () => {
        const local = job({ id: 'job-9', source: 'sse', updatedAt: NOW - 1000 });
        const server = job({ id: 'job-9', source: 'system', updatedAt: NOW });

        const timeline = buildTimelineItems([], [local, server]);

        expect(timeline).toHaveLength(1);
        expect(timeline[0].meta?.source).toBe('system');
    });

    it('deduplicates local and server job ids that describe the same event', () => {
        const local = job({ id: 'reclassify:event-12', source: 'sse', updatedAt: NOW - 1000 });
        const server = job({ id: 'video:event-12', kind: 'video_analysis', source: 'system', updatedAt: NOW });

        const timeline = buildTimelineItems([], [local, server]);

        expect(timeline).toHaveLength(1);
        expect(timeline[0].id).toBe('video:event-12');
    });

    it('does not move an active process row when only its progress heartbeat changes', () => {
        const detection = item({ id: 'bird-1', timestamp: NOW - 500 });
        const first = buildTimelineItems([], [job({ id: 'job-1', startedAt: NOW - 1000, updatedAt: NOW })]);
        const second = buildTimelineItems(
            [detection],
            [job({ id: 'job-1', current: 2, startedAt: NOW - 1000, updatedAt: NOW + 5000 })]
        );

        expect(first[0].timestamp).toBe(NOW - 1000);
        expect(second.map((row) => row.id)).toEqual(['bird-1', 'job-1']);
        expect(second[1].timestamp).toBe(NOW - 1000);
    });

    it('counts every bucket so a chip can state its size before it is applied', () => {
        const counts = countByFilter([
            item({ id: '1', type: 'detection' }),
            item({ id: '2', type: 'detection' }),
            item({ id: '3', type: 'update' }),
            item({ id: '4', type: 'process', meta: { current: 1, total: 2 } }),
            item({ id: '5', type: 'process', meta: { kind: 'error' } })
        ]);
        expect(counts).toEqual({ all: 5, birds: 2, updates: 1, jobs: 1, errors: 1 });
    });

    it('groups by age, newest first, and drops empty groups', () => {
        const groups = groupNotifications(
            [
                item({ id: 'old', timestamp: NOW - 5 * 24 * 3600_000 }),
                item({ id: 'recent', timestamp: NOW - 60_000 }),
                item({ id: 'morning', timestamp: new Date('2026-08-13T08:00:00').getTime() }),
                item({ id: 'newest', timestamp: NOW - 1000 })
            ],
            NOW
        );
        expect(groups.map((g) => g.key)).toEqual(['now', 'earlier', 'older']);
        expect(groups[0].items.map((i) => i.id)).toEqual(['newest', 'recent']);
        // "yesterday" had nothing in it and must not render as a bare heading.
        expect(groups.some((g) => g.key === 'yesterday')).toBe(false);
    });

    it('uses calendar-day boundaries across daylight-saving changes', () => {
        const afterClocksChange = new Date(2026, 9, 26, 12, 0, 0).getTime();
        const earlyYesterday = new Date(2026, 9, 25, 0, 30, 0).getTime();

        expect(groupNotifications([item({ id: 'dst', timestamp: earlyYesterday })], afterClocksChange)[0]?.key)
            .toBe('yesterday');
    });

    it('refuses to invent a percentage from a missing or zero total', () => {
        expect(progressOf(item({ id: 'p1' }))).toBeNull();
        expect(progressOf(item({ id: 'p2', meta: { current: 3, total: 0 } }))).toBeNull();
        expect(progressOf(item({ id: 'p3', meta: { current: 3, total: 4 } }))?.percent).toBe(75);
    });

    it('marks jobs and errors as owner only', () => {
        expect(isOwnerOnlyFilter('jobs')).toBe(true);
        expect(isOwnerOnlyFilter('errors')).toBe(true);
        expect(isOwnerOnlyFilter('birds')).toBe(false);
        expect(isOwnerOnlyFilter('all')).toBe(false);
    });
});
