import { beforeEach, describe, expect, it, vi } from 'vitest';
import { notificationCenter } from './notification_center.svelte';

describe('notificationCenter access filtering', () => {
    beforeEach(() => {
        notificationCenter.clear();
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-03-06T20:00:00.000Z'));
    });

    it('removes owner-only operational items for guest/public sessions', () => {
        notificationCenter.add({
            id: 'detection:1',
            type: 'detection',
            title: 'Bird detected',
            meta: { source: 'sse', route: '/events?event=1' }
        });
        notificationCenter.add({
            id: 'system:health',
            type: 'system',
            title: 'System health degraded',
            meta: { source: 'health', route: '/settings' }
        });
        notificationCenter.add({
            id: 'reclassify:progress',
            type: 'process',
            title: 'Batch analysis',
            meta: { source: 'sse', route: '/settings/data' }
        });
        notificationCenter.add({
            id: 'settings:updated',
            type: 'update',
            title: 'Settings updated',
            meta: { source: 'sse', route: '/settings' }
        });

        notificationCenter.filterForAccess(false);

        expect(notificationCenter.items.map((item) => item.id)).toEqual(['detection:1']);
    });

    it('keeps existing items when owner access is available', () => {
        notificationCenter.add({
            id: 'system:health',
            type: 'system',
            title: 'System health degraded',
            meta: { source: 'health', route: '/settings' }
        });

        notificationCenter.filterForAccess(true);

        expect(notificationCenter.items.map((item) => item.id)).toEqual(['system:health']);
    });

    it('orders notifications by newest timestamp first', () => {
        notificationCenter.add({
            id: 'newer',
            type: 'update',
            title: 'Newer',
            timestamp: 2000,
            meta: { source: 'ui' }
        });
        notificationCenter.add({
            id: 'older',
            type: 'update',
            title: 'Older',
            timestamp: 1000,
            meta: { source: 'ui' }
        });

        expect(notificationCenter.items.map((item) => item.id)).toEqual(['newer', 'older']);
    });
});

describe('stopped jobs in the history', () => {
    beforeEach(() => {
        notificationCenter.clear();
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-09-10T08:00:00.000Z'));
    });

    it('reads a job written off by an older build as a stopped job dated from the write-off', () => {
        const writtenOffAt = Date.now() - 2 * 60 * 60 * 1000;
        // Exactly what an older build persisted: a read "update" flagged stale, progress still attached.
        notificationCenter.add({
            id: 'reclassify:progress:abc',
            type: 'update',
            title: 'Reclassify',
            message: 'Analyzing 11/30 • stale',
            timestamp: writtenOffAt,
            read: true,
            meta: { source: 'sse', current: 11, total: 30, stale: true }
        });
        expect(notificationCenter.items).toHaveLength(1);
        expect(notificationCenter.items[0].type).toBe('process');
        expect(notificationCenter.items[0].meta?.status).toBe('stopped');
        expect(notificationCenter.items[0].meta?.stopped_at).toBe(writtenOffAt);
    });

    it('lets a stopped job go a day after it stopped, and keeps a fresher one', () => {
        const now = Date.now();
        notificationCenter.add({
            id: 'old',
            type: 'process',
            title: 'Reclassify',
            timestamp: now - 5 * 24 * 60 * 60 * 1000,
            read: true,
            meta: { status: 'stopped', stopped_at: now - 5 * 24 * 60 * 60 * 1000 }
        });
        notificationCenter.add({
            id: 'recent',
            type: 'process',
            title: 'Reclassify',
            timestamp: now - 3 * 60 * 60 * 1000,
            read: true,
            meta: { status: 'stopped', stopped_at: now - 2 * 60 * 60 * 1000 }
        });
        expect(notificationCenter.items.map((item) => item.id)).toEqual(['recent']);

        vi.setSystemTime(new Date(now + 23 * 60 * 60 * 1000));
        notificationCenter.expireStoppedJobs();
        expect(notificationCenter.items.map((item) => item.id)).toEqual([]);
    });
});
