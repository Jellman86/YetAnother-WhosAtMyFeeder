import type { AnalysisStatus } from '../api/maintenance';
import type { JobProgressItem } from '../stores/job_progress.svelte';
import type { JobPipelineKindRow } from './pipeline';

export type JobsTranslateFn = (key: string, values?: Record<string, unknown>, fallback?: string) => string;

export interface PresentedActiveJob {
    activityLabel: string;
    progressLabel: string;
    capacityLabel: string | null;
    blockerLabel: string | null;
    freshnessLabel: string;
    determinate: boolean;
    percent: number | null;
    isStale: boolean;
}

export interface PresentedPipelineKindRow {
    activityLabel: string;
    capacityLabel: string | null;
    blockerLabel: string | null;
}

function normalizeCount(value: unknown): number {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return 0;
    return Math.max(0, Math.floor(parsed));
}

function formatAge(ms: number): string {
    const seconds = Math.max(0, Math.floor(ms / 1000));
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remSeconds = seconds % 60;
    if (minutes < 60) return `${minutes}m ${remSeconds}s`;
    const hours = Math.floor(minutes / 60);
    const remMinutes = minutes % 60;
    return `${hours}h ${remMinutes}m`;
}

function formatProgress(current: number, total: number, unit: string, t: JobsTranslateFn): string {
    return t('jobs.progress_units', {
        current: current.toLocaleString(),
        total: total.toLocaleString(),
        unit
    }, '{current} / {total} {unit}');
}

function resolveProgressUnit(job: JobProgressItem): string {
    if (job.kind === 'reclassify') return 'frames';
    return 'items';
}

function resolveActivityLabel(
    job: JobProgressItem,
    row: JobPipelineKindRow | null,
    analysisStatus: AnalysisStatus | null | undefined,
    t: JobsTranslateFn
): string {
    if (job.kind === 'reclassify') {
        if (analysisStatus?.circuit_open) {
            return t('jobs.activity_circuit_open', undefined, 'Paused by circuit breaker');
        }
        if (row?.throttledForMqttPressure && job.current <= 0) {
            return t('jobs.activity_waiting_slots', undefined, 'Waiting for classifier slots');
        }
        return t('jobs.activity_reclassify_running', undefined, 'Analyzing clips');
    }
    if (typeof job.message === 'string' && job.message.trim().length > 0) {
        return job.message.trim();
    }
    return t('jobs.activity_processing', undefined, 'Processing work');
}

function resolveCapacityLabel(row: JobPipelineKindRow | null, t: JobsTranslateFn): string | null {
    if (!row) return null;
    const configured = normalizeCount(row.maxConcurrentConfigured);
    const effective = normalizeCount(row.maxConcurrentEffective);
    const running = normalizeCount(row.running);
    const capacity = row.throttledForMqttPressure && effective > 0
        ? effective
        : (configured > 0 ? configured : effective);
    if (capacity > 0) {
        return t('jobs.capacity_worker_slots', {
            running: running.toLocaleString(),
            capacity: capacity.toLocaleString()
        }, '{running} of {capacity} worker slots busy');
    }
    return null;
}

function resolveBlockerLabel(
    row: JobPipelineKindRow | null,
    analysisStatus: AnalysisStatus | null | undefined,
    t: JobsTranslateFn
): string | null {
    if (analysisStatus?.circuit_open) {
        return t('jobs.blocker_circuit_open', undefined, 'Recent failures paused reclassification work');
    }
    if (row?.throttledForMqttPressure) {
        return t('jobs.blocker_mqtt_pressure', undefined, 'MQTT pressure reduced background capacity');
    }
    return null;
}

export function presentActiveJob(
    job: JobProgressItem,
    row: JobPipelineKindRow | null,
    analysisStatus: AnalysisStatus | null | undefined,
    nowTs: number,
    t: JobsTranslateFn
): PresentedActiveJob {
    const determinate = job.total > 0;
    const percent = determinate ? Math.min(100, Math.max(0, Math.round((job.current / job.total) * 100))) : null;
    const progressLabel = determinate
        ? formatProgress(job.current, job.total, resolveProgressUnit(job), t)
        : t('jobs.progress_expanding', undefined, 'Total work still expanding');
    const age = formatAge(Math.max(0, nowTs - job.updatedAt));
    const isStale = job.status === 'stale';
    const freshnessLabel = isStale
        ? t('jobs.freshness_stale', { age }, 'No update for {age}')
        : t('jobs.freshness_updated', { age }, 'Updated {age} ago');

    return {
        activityLabel: resolveActivityLabel(job, row, analysisStatus, t),
        progressLabel,
        capacityLabel: resolveCapacityLabel(row, t),
        blockerLabel: resolveBlockerLabel(row, analysisStatus, t),
        freshnessLabel,
        determinate,
        percent,
        isStale
    };
}

export function presentPipelineKindRow(
    row: JobPipelineKindRow,
    analysisStatus: AnalysisStatus | null | undefined,
    t: JobsTranslateFn
): PresentedPipelineKindRow {
    const activityLabel = analysisStatus?.circuit_open
        ? t('jobs.activity_circuit_open', undefined, 'Paused by circuit breaker')
        : row.running > 0
            ? t('jobs.activity_processing', undefined, 'Processing work')
            : t('jobs.activity_queued', undefined, 'Waiting in queue');

    return {
        activityLabel,
        capacityLabel: resolveCapacityLabel(row, t),
        blockerLabel: resolveBlockerLabel(row, analysisStatus, t)
    };
}
