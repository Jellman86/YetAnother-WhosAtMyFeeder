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
            meta: { source: 'sse', route: '/settings#data' }
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
});
