import type { BackfillJobStatus } from '../api/backfill';
import { jobProgressStore } from '../stores/job_progress.svelte';

import {
    formatBackfillProgressSummary,
    resolveRunningBackfillMessage,
    updateScopedBackfillProgress,
    type ScopedBackfillProgress,
} from './progress';

export type BackfillKind = 'detections' | 'weather';

function safeCount(value: unknown): number {
    const parsed = Number(value ?? 0);
    return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
}

function settleObsoleteBackfillJobs(prefix: string, keepId?: string) {
    for (const item of jobProgressStore.activeJobs) {
        if (!item.id.startsWith(prefix)) continue;
        if (keepId && item.id === keepId) continue;
        const completedTotal = Math.max(safeCount(item.total), safeCount(item.current));
        if (completedTotal > 0) {
            jobProgressStore.markCompleted({
                id: item.id,
                kind: item.kind,
                title: item.title,
                message: item.message,
                route: item.route,
                current: completedTotal,
                total: completedTotal,
                source: 'poll'
            });
            continue;
        }
        jobProgressStore.remove(item.id);
    }
}

export function syncBackfillJobProgress(
    kind: BackfillKind,
    previous: ScopedBackfillProgress,
    status: BackfillJobStatus | null
): ScopedBackfillProgress {
    const next = updateScopedBackfillProgress(previous, status);
    const prefix = `backfill:${kind}:`;

    if (!status) {
        settleObsoleteBackfillJobs(prefix);
        return next;
    }

    const id = `backfill:${kind}:${status.id || 'unknown'}`;
    settleObsoleteBackfillJobs(prefix, id);
    const processed = safeCount(status.processed);
    const total = safeCount(status.total);
    const updated = kind === 'weather'
        ? safeCount(status.updated)
        : safeCount(status.new_detections);
    const skipped = safeCount(status.skipped);
    const errors = safeCount(status.errors);
    const normalizedTotal = total > 0 ? total : safeCount(next.total);
    const progressTotal = normalizedTotal > 0
        ? normalizedTotal
        : (status.status === 'running' ? 0 : processed);
    const title = kind === 'weather' ? 'Weather Backfill' : 'Detection Backfill';
    const message = status.status === 'running'
        ? resolveRunningBackfillMessage(
            status,
            formatBackfillProgressSummary(processed, normalizedTotal, updated, skipped, errors)
        )
        : (status.message || formatBackfillProgressSummary(processed, normalizedTotal, updated, skipped, errors));

    if (status.status === 'completed') {
        jobProgressStore.markCompleted({
            id,
            kind: kind === 'weather' ? 'weather_backfill' : 'backfill',
            title,
            message,
            route: '/settings',
            current: processed,
            total: progressTotal,
            source: 'poll',
        });
        return next;
    }

    if (status.status === 'failed') {
        jobProgressStore.markFailed({
            id,
            kind: kind === 'weather' ? 'weather_backfill' : 'backfill',
            title,
            message,
            route: '/settings',
            current: processed,
            total: progressTotal,
            source: 'poll',
        });
        return next;
    }

    jobProgressStore.upsertRunning({
        id,
        kind: kind === 'weather' ? 'weather_backfill' : 'backfill',
        title,
        message,
        route: '/settings',
        current: processed,
        total: progressTotal,
        source: 'poll',
    });
    return next;
}
