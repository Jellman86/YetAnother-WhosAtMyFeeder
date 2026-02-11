export interface NotificationItem {
    id: string;
    type: 'detection' | 'update' | 'process' | 'system';
    title: string;
    message?: string;
    timestamp: number;
    read: boolean;
    meta?: Record<string, any>;
}

const STORAGE_KEY = 'yawamf_notification_center';
const MAX_ITEMS = 50;

class NotificationCenterStore {
    items = $state<NotificationItem[]>([]);

    hydrate() {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY);
            if (!raw) return;
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) {
                this.items = parsed.slice(0, MAX_ITEMS);
            }
        } catch {
            // ignore storage errors
        }
    }

    persist() {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(this.items.slice(0, MAX_ITEMS)));
        } catch {
            // ignore storage errors
        }
    }

    add(item: Omit<NotificationItem, 'timestamp' | 'read'> & { timestamp?: number; read?: boolean }) {
        const entry: NotificationItem = {
            ...item,
            timestamp: item.timestamp ?? Date.now(),
            read: item.read ?? false
        };
        this.items = [entry, ...this.items].slice(0, MAX_ITEMS);
        this.persist();
        return entry.id;
    }

    upsert(item: NotificationItem) {
        const idx = this.items.findIndex((existing) => existing.id === item.id);
        if (idx >= 0) {
            const updated = [...this.items];
            updated[idx] = item;
            this.items = updated;
        } else {
            this.items = [item, ...this.items].slice(0, MAX_ITEMS);
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
        this.persist();
    }
}

export const notificationCenter = new NotificationCenterStore();
