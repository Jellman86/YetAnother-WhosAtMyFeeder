export type NotificationSource = 'sse' | 'health' | 'cache' | 'system' | 'ui';

export interface NotificationMeta {
    source?: NotificationSource;
    route?: string;
    event_id?: string;
    current?: number;
    total?: number;
    processed?: number;
    kind?: string;
    stale?: boolean;
    open_label?: string;
}

export interface NotificationItem {
    id: string;
    type: 'detection' | 'update' | 'process' | 'system';
    title: string;
    message?: string;
    timestamp: number;
    read: boolean;
    meta?: NotificationMeta;
}

const STORAGE_KEY = 'yawamf_notification_center';
const MAX_ITEMS = 50;

class NotificationCenterStore {
    items = $state<NotificationItem[]>([]);
    private fallbackCounter = 0;
    private persistTimer: number | null = null;

    private coerceType(value: unknown): NotificationItem['type'] {
        if (value === 'detection' || value === 'update' || value === 'process' || value === 'system') {
            return value;
        }
        return 'system';
    }

    private normalize(items: unknown[]): NotificationItem[] {
        const seen = new Set<string>();
        const normalized: NotificationItem[] = [];
        for (const raw of items) {
            if (!raw || typeof raw !== 'object') continue;
            const candidate = raw as Partial<NotificationItem>;
            const rawId = typeof candidate.id === 'string' ? candidate.id.trim() : '';
            const id = rawId || `notif:fallback:${Date.now()}:${this.fallbackCounter++}`;
            if (seen.has(id)) continue;
            seen.add(id);
            normalized.push({
                id,
                type: this.coerceType(candidate.type),
                title: typeof candidate.title === 'string' && candidate.title.trim().length > 0
                    ? candidate.title
                    : 'Notification',
                message: candidate.message === undefined || candidate.message === null
                    ? undefined
                    : String(candidate.message),
                timestamp: Number.isFinite(Number(candidate.timestamp))
                    ? Number(candidate.timestamp)
                    : Date.now(),
                read: Boolean(candidate.read),
                meta: candidate.meta && typeof candidate.meta === 'object'
                    ? candidate.meta
                    : undefined
            });
            if (normalized.length >= MAX_ITEMS) break;
        }
        return normalized;
    }

    hydrate() {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY);
            if (!raw) return;
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) {
                this.items = this.normalize(parsed);
            }
        } catch {
            // ignore storage errors
        }
    }

    persist() {
        if (typeof window === 'undefined') return;
        if (this.persistTimer !== null) return;
        this.persistTimer = window.setTimeout(() => {
            this.persistTimer = null;
            try {
                window.localStorage.setItem(STORAGE_KEY, JSON.stringify(this.items.slice(0, MAX_ITEMS)));
            } catch {
                // ignore storage errors
            }
        }, 150);
    }

    add(item: Omit<NotificationItem, 'timestamp' | 'read'> & { timestamp?: number; read?: boolean }) {
        const rawEntry: NotificationItem = {
            ...item,
            timestamp: item.timestamp ?? Date.now(),
            read: item.read ?? false
        };
        const entry = this.normalize([rawEntry])[0];
        if (!entry) return '';
        this.items = this.normalize([entry, ...this.items]);
        this.persist();
        return entry.id;
    }

    upsert(item: NotificationItem) {
        const normalized = this.normalize([item])[0];
        if (!normalized) return;
        const idx = this.items.findIndex((existing) => existing.id === normalized.id);
        const next = this.items.filter((existing) => existing.id !== normalized.id);
        if (idx >= 0) {
            this.items = this.normalize([normalized, ...next]);
        } else {
            this.items = this.normalize([normalized, ...this.items]);
        }
        this.persist();
    }

    markRead(id: string) {
        this.items = this.items.map((item) => (item.id === id ? { ...item, read: true } : item));
        this.persist();
    }

    markAllRead() {
        this.items = this.items.map((item) => ({ ...item, read: true }));
        this.persist();
    }

    remove(id: string) {
        this.items = this.items.filter((item) => item.id !== id);
        this.persist();
    }

    clear() {
        this.items = [];
        if (this.persistTimer !== null && typeof window !== 'undefined') {
            window.clearTimeout(this.persistTimer);
            this.persistTimer = null;
        }
        this.persist();
    }
}

export const notificationCenter = new NotificationCenterStore();
