import type { NotificationItem } from '../stores/notification_center.svelte';

const MAX_POLICY_ENTRIES = 500;
const ENTRY_TTL_MS = 24 * 60 * 60 * 1000;

export class NotificationPolicy {
    private throttle = new Map<string, number>();
    private signature = new Map<string, string>();

    shouldEmit(id: string, sig: string, throttleMs = 0): boolean {
        this.prune();
        const now = Date.now();
        const lastSig = this.signature.get(id);
        const lastAt = this.throttle.get(id) ?? 0;
        if (lastSig === sig && now - lastAt < throttleMs) {
            return false;
        }
        this.signature.set(id, sig);
        this.throttle.set(id, now);
        this.enforceCap();
        return true;
    }

    settleStale(items: NotificationItem[], staleAgeMs: number): NotificationItem[] {
        const now = Date.now();
        return items
            .filter((item) => item.type === 'process' && !item.read && now - item.timestamp > staleAgeMs)
            .map((item) => ({
                ...item,
                type: 'update' as const,
                read: true,
                timestamp: now,
                message: item.message ? `${item.message} • stale` : 'Stale process notification',
                meta: {
                    ...(item.meta ?? {}),
                    stale: true,
                    source: item.meta?.source ?? 'system',
                },
            }));
    }

    private prune(): void {
        const cutoff = Date.now() - ENTRY_TTL_MS;
        for (const [id, ts] of this.throttle.entries()) {
            if (ts >= cutoff) continue;
            this.throttle.delete(id);
            this.signature.delete(id);
        }
    }

    private enforceCap(): void {
        if (this.throttle.size <= MAX_POLICY_ENTRIES) return;
        const sorted = [...this.throttle.entries()].sort((a, b) => a[1] - b[1]);
        const over = this.throttle.size - MAX_POLICY_ENTRIES;
        for (let i = 0; i < over; i += 1) {
            const id = sorted[i]?.[0];
            if (!id) continue;
            this.throttle.delete(id);
            this.signature.delete(id);
        }
    }
}

export const notificationPolicy = new NotificationPolicy();
