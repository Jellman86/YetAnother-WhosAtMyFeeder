import type { BackfillJobStatus } from '../api';

export interface ScopedBackfillProgress {
    jobId: string | null;
    total: number;
}

function safeCount(value: unknown): number {
    const parsed = Number(value ?? 0);
    return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
}

function normalizeJobId(value: unknown): string | null {
    if (typeof value !== 'string') return null;
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
}

function normalizeMessage(value: unknown): string {
    if (typeof value !== 'string') return '';
    return value.trim();
}

export function updateScopedBackfillProgress(
    previous: ScopedBackfillProgress,
    status: Pick<BackfillJobStatus, 'id' | 'status' | 'processed' | 'total'> | null
): ScopedBackfillProgress {
    if (!status) {
        return {
            jobId: null,
            total: 0
        };
    }

    const nextJobId = normalizeJobId(status.id);
    const processed = safeCount(status.processed);
    const reportedTotal = safeCount(status.total);
    const isSameJob = nextJobId !== null && nextJobId === previous.jobId;

    if (reportedTotal > 0) {
        return {
            jobId: nextJobId,
            total: Math.max(reportedTotal, processed)
        };
    }

    if (status.status !== 'running') {
        return {
            jobId: nextJobId,
            total: processed
        };
    }

    if (isSameJob) {
        return {
            jobId: nextJobId,
            total: previous.total > 0
                ? Math.max(previous.total, processed)
                : processed
        };
    }

    return {
        jobId: nextJobId,
        total: 0
    };
}

export function resolveRunningBackfillMessage(
    status: Pick<BackfillJobStatus, 'status' | 'message'> | null,
    fallbackSummary: string
): string {
    const fallback = normalizeMessage(fallbackSummary);
    if (!status) return fallback;
    if (normalizeMessage(status.status).toLowerCase() !== 'running') return fallback;
    return normalizeMessage(status.message) || fallback;
}

export function formatBackfillProgressSummary(
    processed: number,
    total: number,
    updated: number,
    skipped: number,
    errors: number
): string {
    const normalizedProcessed = safeCount(processed);
    const normalizedTotal = safeCount(total);
    const normalizedUpdated = safeCount(updated);
    const normalizedSkipped = safeCount(skipped);
    const normalizedErrors = safeCount(errors);
    const totalLabel = normalizedTotal > 0
        ? normalizedTotal.toLocaleString()
        : '?';

    return `${normalizedProcessed.toLocaleString()}/${totalLabel} • ${normalizedUpdated.toLocaleString()} upd • ${normalizedSkipped.toLocaleString()} skip • ${normalizedErrors.toLocaleString()} err`;
}
