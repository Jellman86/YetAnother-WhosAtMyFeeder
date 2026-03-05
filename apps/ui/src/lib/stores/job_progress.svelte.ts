export type JobStatus = 'running' | 'stale' | 'completed' | 'failed';
export type JobSource = 'sse' | 'poll' | 'ui' | 'system';

export interface JobProgressItem {
    id: string;
    kind: string;
    title: string;
    message?: string;
    route?: string;
    status: JobStatus;
    current: number;
    total: number;
    startedAt: number;
    updatedAt: number;
    finishedAt?: number;
    ratePerMinute?: number;
    etaSeconds?: number;
    source: JobSource;
}

export interface JobProgressUpdateInput {
    id: string;
    kind: string;
    title: string;
    message?: string;
    route?: string;
    current?: number;
    total?: number;
    source?: JobSource;
    timestamp?: number;
}

export interface JobProgressTerminalInput {
    id: string;
    kind: string;
    title: string;
    message?: string;
    route?: string;
    current?: number;
    total?: number;
    source?: JobSource;
    timestamp?: number;
}

const MAX_HISTORY_ITEMS = 100;

class JobProgressStore {
    items = $state<JobProgressItem[]>([]);

    get activeJobs(): JobProgressItem[] {
        return this.items
            .filter((item) => item.status === 'running' || item.status === 'stale')
            .sort((a, b) => b.updatedAt - a.updatedAt);
    }

    get historyJobs(): JobProgressItem[] {
        return this.items
            .filter((item) => item.status === 'completed' || item.status === 'failed')
            .sort((a, b) => (b.finishedAt ?? b.updatedAt) - (a.finishedAt ?? a.updatedAt));
    }

    upsertRunning(input: JobProgressUpdateInput) {
        const id = this.normalizeId(input.id);
        if (!id) return;

        const now = this.normalizeTimestamp(input.timestamp);
        const idx = this.items.findIndex((item) => item.id === id);
        const existing = idx >= 0 ? this.items[idx] : null;
        const currentInput = this.normalizeOptionalCount(input.current);
        const totalInput = this.normalizeOptionalCount(input.total);
        const previousCurrent = existing?.current ?? 0;
        const previousTotal = existing?.total ?? 0;
        const current = currentInput === null
            ? previousCurrent
            : Math.max(previousCurrent, currentInput);
        const totalCandidate = totalInput === null
            ? previousTotal
            : Math.max(0, totalInput);
        const total = Math.max(totalCandidate, current);
        const startedAt = existing?.startedAt ?? now;
        const previousUpdatedAt = existing?.updatedAt ?? startedAt;

        const deltaUnits = Math.max(0, current - previousCurrent);
        const deltaMs = Math.max(1, now - previousUpdatedAt);
        const instantRate = deltaUnits > 0 ? (deltaUnits * 60000) / deltaMs : null;
        const elapsedMs = Math.max(1, now - startedAt);
        const averageRate = current > 0 ? (current * 60000) / elapsedMs : null;
        const existingRate = Number.isFinite(existing?.ratePerMinute) ? (existing?.ratePerMinute as number) : null;
        const blendedRate = this.pickRate(existingRate, instantRate, averageRate);
        const etaSeconds = this.computeEtaSeconds(current, total, blendedRate);

        const next: JobProgressItem = {
            id,
            kind: this.normalizeKind(input.kind),
            title: input.title || existing?.title || 'Job',
            message: input.message ?? existing?.message,
            route: input.route ?? existing?.route,
            status: 'running',
            current,
            total,
            startedAt,
            updatedAt: now,
            ratePerMinute: blendedRate ?? undefined,
            etaSeconds: etaSeconds ?? undefined,
            source: input.source ?? existing?.source ?? 'sse'
        };

        const withoutFinished = { ...next };
        delete withoutFinished.finishedAt;
        this.upsert(withoutFinished);
    }

    markCompleted(input: JobProgressTerminalInput) {
        this.markTerminal('completed', input);
    }

    markFailed(input: JobProgressTerminalInput) {
        this.markTerminal('failed', input);
    }

    markStale(maxIdleMs: number) {
        const threshold = Number.isFinite(maxIdleMs) ? Math.max(1000, Math.floor(maxIdleMs)) : 90_000;
        const now = Date.now();
        let changed = false;
        const next = this.items.map((item) => {
            if (item.status !== 'running') return item;
            if (now - item.updatedAt <= threshold) return item;
            changed = true;
            return {
                ...item,
                status: 'stale' as const,
                etaSeconds: undefined
            };
        });
        if (changed) {
            this.items = next;
        }
    }

    remove(id: string) {
        const normalized = this.normalizeId(id);
        if (!normalized) return;
        this.items = this.items.filter((item) => item.id !== normalized);
    }

    closeActiveByPrefix(prefix: string, status: 'completed' | 'failed' | 'stale' = 'completed') {
        const normalizedPrefix = typeof prefix === 'string' ? prefix.trim() : '';
        if (!normalizedPrefix) return;
        const now = Date.now();
        let changed = false;
        const next = this.items.map((item) => {
            if (!item.id.startsWith(normalizedPrefix)) return item;
            if (item.status === status) return item;
            if (item.status === 'completed' || item.status === 'failed') return item;
            changed = true;
            return {
                ...item,
                status,
                updatedAt: now,
                etaSeconds: undefined,
                finishedAt: status === 'stale' ? item.finishedAt : now
            };
        });
        if (!changed) return;
        this.items = next;
        this.enforceHistoryCap();
    }

    clearHistory() {
        this.items = this.items.filter((item) => item.status === 'running' || item.status === 'stale');
    }

    clearAll() {
        this.items = [];
    }

    private markTerminal(status: 'completed' | 'failed', input: JobProgressTerminalInput) {
        const id = this.normalizeId(input.id);
        if (!id) return;
        const idx = this.items.findIndex((item) => item.id === id);
        const existing = idx >= 0 ? this.items[idx] : null;
        const now = this.normalizeTimestamp(input.timestamp);
        const fallbackCurrent = existing?.current ?? 0;
        const fallbackTotal = existing?.total ?? 0;
        const current = this.normalizeCount(input.current, fallbackCurrent);
        const total = this.normalizeCount(input.total, fallbackTotal);

        const next: JobProgressItem = {
            id,
            kind: this.normalizeKind(input.kind || existing?.kind || 'job'),
            title: input.title || existing?.title || 'Job',
            message: input.message ?? existing?.message,
            route: input.route ?? existing?.route,
            status,
            current: status === 'completed' && total > 0 ? Math.max(current, total) : current,
            total,
            startedAt: existing?.startedAt ?? now,
            updatedAt: now,
            finishedAt: now,
            ratePerMinute: existing?.ratePerMinute,
            etaSeconds: undefined,
            source: input.source ?? existing?.source ?? 'sse'
        };

        this.upsert(next);
        this.enforceHistoryCap();
    }

    private upsert(item: JobProgressItem) {
        const idx = this.items.findIndex((existing) => existing.id === item.id);
        if (idx >= 0) {
            const next = [...this.items];
            next[idx] = item;
            this.items = next;
            return;
        }
        this.items = [item, ...this.items];
    }

    private enforceHistoryCap() {
        const active = this.items.filter((item) => item.status === 'running' || item.status === 'stale');
        const history = this.items
            .filter((item) => item.status === 'completed' || item.status === 'failed')
            .sort((a, b) => (b.finishedAt ?? b.updatedAt) - (a.finishedAt ?? a.updatedAt))
            .slice(0, MAX_HISTORY_ITEMS);
        this.items = [...active, ...history];
    }

    private normalizeId(value: unknown): string {
        return typeof value === 'string' ? value.trim() : '';
    }

    private normalizeKind(value: unknown): string {
        const parsed = typeof value === 'string' ? value.trim() : '';
        return parsed || 'job';
    }

    private normalizeCount(value: unknown, fallback = 0): number {
        const parsed = Number(value);
        if (!Number.isFinite(parsed)) return Math.max(0, Math.floor(fallback));
        return Math.max(0, Math.floor(parsed));
    }

    private normalizeOptionalCount(value: unknown): number | null {
        if (value === undefined || value === null || value === '') return null;
        const parsed = Number(value);
        if (!Number.isFinite(parsed)) return null;
        return Math.max(0, Math.floor(parsed));
    }

    private normalizeTimestamp(value: unknown): number {
        const parsed = Number(value);
        if (!Number.isFinite(parsed)) return Date.now();
        return Math.max(0, Math.floor(parsed));
    }

    private pickRate(existingRate: number | null, instantRate: number | null, averageRate: number | null): number | null {
        const normalizedExisting = this.normalizeRate(existingRate);
        const normalizedInstant = this.normalizeRate(instantRate);
        const normalizedAverage = this.normalizeRate(averageRate);
        if (normalizedExisting && normalizedInstant) {
            return this.normalizeRate((normalizedExisting * 0.65) + (normalizedInstant * 0.35));
        }
        return normalizedInstant ?? normalizedAverage ?? normalizedExisting ?? null;
    }

    private normalizeRate(value: number | null | undefined): number | null {
        if (!Number.isFinite(value)) return null;
        const normalized = Number(value);
        if (normalized <= 0) return null;
        if (normalized > 1_000_000) return 1_000_000;
        return normalized;
    }

    private computeEtaSeconds(current: number, total: number, ratePerMinute: number | null): number | null {
        if (total <= 0 || current >= total || !ratePerMinute || ratePerMinute <= 0) return null;
        const remaining = total - current;
        const etaMinutes = remaining / ratePerMinute;
        if (!Number.isFinite(etaMinutes) || etaMinutes <= 0) return null;
        const etaSeconds = Math.ceil(etaMinutes * 60);
        if (etaSeconds > 365 * 24 * 60 * 60) return null;
        return etaSeconds;
    }
}

export const jobProgressStore = new JobProgressStore();
