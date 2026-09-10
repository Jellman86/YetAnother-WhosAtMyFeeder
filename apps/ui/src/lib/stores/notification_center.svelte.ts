type NotificationSource = 'sse' | 'health' | 'cache' | 'system' | 'ui' | 'poll';

interface NotificationMeta {
    source?: NotificationSource;
    route?: string;
    event_id?: string;
    current?: number;
    total?: number;
    processed?: number;
    kind?: string;
    status?: 'queued' | 'running' | 'stale' | 'stopped' | 'completed' | 'failed';
    stale?: boolean;
    /** When a quiet job was written off as stopped; it leaves the history a day later. */
    stopped_at?: number;
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
/** A stopped job is a record, not a task: it stays a day so the owner can see what happened, then goes. */
const STOPPED_JOB_TTL_MS = 24 * 60 * 60 * 1000;

function routeIsOwnerOnly(route: string | undefined): boolean {
    if (!route) return false;
    return route.startsWith('/settings')
        || route.startsWith('/notifications/jobs')
        || route.startsWith('/notifications/errors')
        || route.startsWith('/jobs');
}

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

    /**
     * Before the stopped state existed, a quiet job was rewritten into a read "update" flagged
     * `stale`, which kept its progress bar for as long as the browser kept history. Read those
     * back as stopped jobs, dated from when they were written off, so the day-long expiry
     * applies to them too.
     */
    private migrateLegacyStale(candidate: Partial<NotificationItem>): Partial<NotificationItem> {
        const meta = candidate.meta;
        if (!meta || typeof meta !== 'object' || meta.status || meta.stale !== true || candidate.type !== 'update') {
            return candidate;
        }
        const timestamp = Number(candidate.timestamp);
        return {
            ...candidate,
            type: 'process',
            meta: { ...meta, status: 'stopped', stopped_at: Number.isFinite(timestamp) ? timestamp : Date.now() }
        };
    }

    private isExpiredStoppedJob(item: NotificationItem, now: number): boolean {
        if (item.meta?.status !== 'stopped') return false;
        const stoppedAt = Number(item.meta.stopped_at);
        return Number.isFinite(stoppedAt) && now - stoppedAt > STOPPED_JOB_TTL_MS;
    }

    private normalize(items: unknown[]): NotificationItem[] {
        const seen = new Set<string>();
        const normalized: NotificationItem[] = [];
        const now = Date.now();
        for (const raw of items) {
            if (!raw || typeof raw !== 'object') continue;
            const candidate = this.migrateLegacyStale(raw as Partial<NotificationItem>);
            const rawId = typeof candidate.id === 'string' ? candidate.id.trim() : '';
            const id = rawId || `notif:fallback:${Date.now()}:${this.fallbackCounter++}`;
            if (seen.has(id)) continue;
            seen.add(id);
            const entry: NotificationItem = {
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
            };
            if (this.isExpiredStoppedJob(entry, now)) continue;
            normalized.push(entry);
        }
        return normalized
            .sort((left, right) => {
                const timestampDiff = right.timestamp - left.timestamp;
                if (timestampDiff !== 0) return timestampDiff;
                return right.id.localeCompare(left.id);
            })
            .slice(0, MAX_ITEMS);
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

    private isVisibleForAccess(item: NotificationItem, canAccessOwnerItems: boolean): boolean {
        if (canAccessOwnerItems) return true;
        if (item.type === 'process' || item.type === 'system') return false;
        return !routeIsOwnerOnly(item.meta?.route);
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

    /** Drop stopped jobs whose day is up; called from the periodic owner checks. */
    expireStoppedJobs() {
        const next = this.normalize(this.items);
        if (next.length === this.items.length) return;
        this.items = next;
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

    filterForAccess(canAccessOwnerItems: boolean) {
        const filtered = this.items.filter((item) => this.isVisibleForAccess(item, canAccessOwnerItems));
        if (filtered.length === this.items.length) return;
        this.items = filtered;
        this.persist();
    }
}

export const notificationCenter = new NotificationCenterStore();
