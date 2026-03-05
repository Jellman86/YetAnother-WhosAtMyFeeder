import type { JobProgressItem } from '../stores/job_progress.svelte';

export interface QueueTelemetrySnapshot {
    queued: number;
    running?: number;
    queueDepthKnown: boolean;
    updatedAt: number;
}

export type QueueTelemetryByKind = Record<string, QueueTelemetrySnapshot>;

export interface JobPipelineKindRow {
    kind: string;
    queued: number | null;
    queueDepthKnown: boolean;
    running: number;
    stale: number;
    completed: number;
    failed: number;
    queueUpdatedAt: number | null;
}

export interface JobPipelineModel {
    lanes: {
        queuedKnown: number;
        queuedUnknownKinds: number;
        running: number;
        completed: number;
        failed: number;
    };
    kinds: JobPipelineKindRow[];
}

interface MutableCounters {
    running: number;
    stale: number;
    completed: number;
    failed: number;
}

function normalizeCount(value: unknown): number {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return 0;
    return Math.max(0, Math.floor(parsed));
}

function normalizeKind(value: unknown): string {
    if (typeof value !== 'string') return 'job';
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : 'job';
}

function rankKind(row: JobPipelineKindRow): number {
    // Prioritize active/running work, then known queued pressure, then terminal backlog.
    return (row.running * 1000)
        + ((row.queued ?? 0) * 100)
        + (row.failed * 10)
        + row.completed;
}

export function buildJobsPipelineModel(
    activeJobs: JobProgressItem[],
    historyJobs: JobProgressItem[],
    queueByKind: QueueTelemetryByKind = {}
): JobPipelineModel {
    const countersByKind = new Map<string, MutableCounters>();

    const ensure = (kind: string): MutableCounters => {
        const key = normalizeKind(kind);
        const existing = countersByKind.get(key);
        if (existing) return existing;
        const created: MutableCounters = {
            running: 0,
            stale: 0,
            completed: 0,
            failed: 0
        };
        countersByKind.set(key, created);
        return created;
    };

    for (const item of activeJobs) {
        const counters = ensure(item.kind);
        counters.running += 1;
        if (item.status === 'stale') {
            counters.stale += 1;
        }
    }

    for (const item of historyJobs) {
        const counters = ensure(item.kind);
        if (item.status === 'failed') {
            counters.failed += 1;
        } else if (item.status === 'completed') {
            counters.completed += 1;
        }
    }

    for (const kind of Object.keys(queueByKind)) {
        ensure(kind);
    }

    const kinds: JobPipelineKindRow[] = [];
    let queuedKnown = 0;
    let queuedUnknownKinds = 0;
    let running = 0;
    let completed = 0;
    let failed = 0;

    for (const [kind, counters] of countersByKind.entries()) {
        const queue = queueByKind[kind];
        const queueDepthKnown = queue?.queueDepthKnown === true;
        const queued = queueDepthKnown ? normalizeCount(queue?.queued) : null;
        const runningFromQueue = normalizeCount(queue?.running);
        const runningCount = Math.max(counters.running, runningFromQueue);

        const row: JobPipelineKindRow = {
            kind,
            queued,
            queueDepthKnown,
            running: runningCount,
            stale: counters.stale,
            completed: counters.completed,
            failed: counters.failed,
            queueUpdatedAt: queue ? normalizeCount(queue.updatedAt) : null
        };
        kinds.push(row);

        if (queued !== null) {
            queuedKnown += queued;
        } else {
            queuedUnknownKinds += 1;
        }
        running += row.running;
        completed += row.completed;
        failed += row.failed;
    }

    kinds.sort((a, b) => {
        const diff = rankKind(b) - rankKind(a);
        if (diff !== 0) return diff;
        return a.kind.localeCompare(b.kind);
    });

    return {
        lanes: {
            queuedKnown,
            queuedUnknownKinds,
            running,
            completed,
            failed
        },
        kinds
    };
}
