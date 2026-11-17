import { get } from 'svelte/store';
import { _ } from 'svelte-i18n';
import type { BackfillJobStatus } from '../api/backfill';
import { jobProgressStore } from '../stores/job_progress.svelte';

import {
    describeBackfillProgress,
    formatBackfillProgressSummary,
    resolveRunningBackfillMessage,
    updateScopedBackfillProgress,
    type ScopedBackfillProgress,
} from './progress';

export type BackfillKind = 'detections' | 'weather';

function t(key: string, fallback: string): string {
    try {
        return get(_)(key, { default: fallback });
    } catch {
        return fallback;
    }
}

function counted(key: string, values: Record<string, number>): string {
    return get(_)(key, { values });
}

/** The worded summary; the plain English one only before a language has loaded. */
function progressSummary(processed: number, total: number, updated: number, skipped: number, errors: number, added?: number): string {
    try {
        return describeBackfillProgress(counted, processed, total, updated, skipped, errors, added);
    } catch {
        return formatBackfillProgressSummary(processed, total, updated, skipped, errors, added);
    }
}

function safeCount(value: unknown): number {
    const parsed = Number(value ?? 0);
    return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
}

function settleObsoleteBackfillJobs(prefix: string, keepId?: string) {
    for (const item of jobProgressStore.activeJobs) {
        if (!item.id.startsWith(prefix)) continue;
        if (keepId && item.id === keepId) continue;
        jobProgressStore.upsertRunning({
            id: item.id,
            kind: item.kind,
            title: item.title,
            message: t(
                'jobs.backfill_status_unavailable',
                'The status was lost when YA-WAMF restarted or your sign-in changed, so the job may have been interrupted. Start it again if its result is missing.'
            ),
            route: item.route,
            current: item.current,
            total: item.total,
            source: 'poll'
        });
        jobProgressStore.closeActiveByPrefix(item.id, 'stale');
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
    const updated = safeCount(status.updated);
    const newDetections = kind === 'weather' ? undefined : safeCount(status.new_detections);
    const skipped = safeCount(status.skipped);
    const errors = safeCount(status.errors);
    const normalizedTotal = total > 0 ? total : safeCount(next.total);
    const progressTotal = normalizedTotal > 0
        ? normalizedTotal
        : (status.status === 'running' ? 0 : processed);
    const title = kind === 'weather'
        ? t('jobs.kind_weather_backfill', 'Missing weather')
        : t('jobs.kind_backfill', 'Import of missed visits');
    const message = status.status === 'running'
        ? resolveRunningBackfillMessage(
            status,
            progressSummary(processed, normalizedTotal, updated, skipped, errors, newDetections)
        )
        : progressSummary(processed, normalizedTotal, updated, skipped, errors, newDetections);

    if (status.status === 'completed') {
        jobProgressStore.markCompleted({
            id,
            kind: kind === 'weather' ? 'weather_backfill' : 'backfill',
            // A backfill row carries the server's own job id, so the server's count already includes it.
            serverJobId: id,
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
            // A backfill row carries the server's own job id, so the server's count already includes it.
            serverJobId: id,
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
        // A backfill row carries the server's own job id, so the server's count already includes it.
        serverJobId: id,
        title,
        message,
        route: '/settings',
        current: processed,
        total: progressTotal,
        source: 'poll',
    });
    return next;
}
