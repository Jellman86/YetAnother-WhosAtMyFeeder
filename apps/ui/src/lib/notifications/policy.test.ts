import { describe, expect, it } from 'vitest';
import { notificationPolicy } from './policy';
import type { NotificationItem } from '../stores/notification_center.svelte';

const quietSince = 1_000_000;
const running: NotificationItem = {
    id: 'reclassify:progress:abc',
    type: 'process',
    title: 'Reclassify',
    message: 'Analyzing 11/30',
    timestamp: quietSince,
    read: false,
    meta: { source: 'sse', route: '/events?event=abc', current: 11, total: 30 }
};

describe('settling a job that stopped reporting', () => {
    it('writes it off as a stopped process at the time it went quiet, not as an update stamped now', () => {
        const now = quietSince + 46 * 60 * 1000;
        const [settled] = notificationPolicy.settleStale([running], 45 * 60 * 1000, now);
        expect(settled.type).toBe('process');
        expect(settled.timestamp).toBe(quietSince);
        expect(settled.read).toBe(true);
        expect(settled.meta?.status).toBe('stopped');
        expect(settled.meta?.stopped_at).toBe(now);
        expect(settled.meta?.current).toBe(11);
        // The message is left alone; the page states the stopped fact from the status.
        expect(settled.message).toBe('Analyzing 11/30');
        expect(settled.message).not.toContain('stale');
    });

    it('leaves a job alone while it is still inside the window, or once it has been read', () => {
        const soon = quietSince + 10 * 60 * 1000;
        expect(notificationPolicy.settleStale([running], 45 * 60 * 1000, soon)).toHaveLength(0);
        const seen = { ...running, read: true };
        expect(notificationPolicy.settleStale([seen], 45 * 60 * 1000, quietSince + 60 * 60 * 1000)).toHaveLength(0);
    });
});
