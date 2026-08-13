import { describe, expect, it } from 'vitest';
import type { NotificationItem } from '../stores/notification_center.svelte';
import {
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

describe('notification timeline', () => {
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
