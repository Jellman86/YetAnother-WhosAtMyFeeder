import type { NotificationItem } from '../stores/notification_center.svelte';

const MAX_POLICY_ENTRIES = 500;
const ENTRY_TTL_MS = 24 * 60 * 60 * 1000;

class NotificationPolicy {
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

    /**
     * A process that has reported nothing for the stale window is written off as stopped. It
     * stays a process, keeps the time of its last progress (so it sits where it went quiet in the
     * timeline rather than jumping to "now"), and records when it was written off so the history
     * can let it go a day later. The page says what happened from `status`; the stored message is
     * left alone.
     */
    settleStale(items: NotificationItem[], staleAgeMs: number, now: number = Date.now()): NotificationItem[] {
        return items
            .filter((item) => item.type === 'process' && !item.read && now - item.timestamp > staleAgeMs)
            .map((item) => ({
                ...item,
                read: true,
                meta: {
                    ...(item.meta ?? {}),
                    status: 'stopped' as const,
                    stopped_at: now,
                    stale: true,
                    source: item.meta?.source ?? 'system'
                }
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
