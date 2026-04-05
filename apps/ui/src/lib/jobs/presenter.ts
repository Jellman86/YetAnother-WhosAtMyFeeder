import type { AnalysisStatus } from '../api/maintenance';
import type { JobProgressItem } from '../stores/job_progress.svelte';
import type { JobPipelineKindRow } from './pipeline';

export type JobsTranslationValues = Record<string, string | number | boolean | Date | null | undefined>;
export type JobsTranslateFn = (key: string, values?: JobsTranslationValues, fallback?: string) => string;

export interface PresentedActiveJob {
    activityLabel: string;
    progressLabel: string;
    capacityLabel: string | null;
    blockerLabel: string | null;
    detailLabel: string | null;
    freshnessLabel: string;
    determinate: boolean;
    percent: number | null;
    isStale: boolean;
}

export interface PresentedJobKindIcon {
    key: 'reclassify' | 'backfill' | 'weather' | 'download' | 'job';
    label: string;
}

export interface PresentedPipelineKindRow {
    activityLabel: string;
    capacityLabel: string | null;
    blockerLabel: string | null;
    queueDepthLabel: string;
    queueCapacityLabel: string | null;
}

export interface PresentedGlobalProgressSummary {
    headline: string;
    subline: string;
    progressLabel: string;
    determinate: boolean;
    percent: number | null;
}

function formatRunningHeadline(count: number, t: JobsTranslateFn): string {
    if (count === 1) {
        return t('jobs.global_running_single', undefined, '1 job running');
    }
    return t('jobs.global_running_multi', { count: count.toLocaleString() }, '{count} jobs running');
}

function supportsReclassifyQueueStatus(kind: string): boolean {
    return kind === 'reclassify' || kind === 'reclassify_batch';
}

export function presentJobKindIcon(kind: string): PresentedJobKindIcon {
    switch (kind) {
        case 'reclassify':
        case 'reclassify_batch':
            return { key: 'reclassify', label: 'Analysis' };
        case 'backfill':
            return { key: 'backfill', label: 'Backfill' };
        case 'weather_backfill':
            return { key: 'weather', label: 'Weather' };
        case 'model_download':
            return { key: 'download', label: 'Download' };
        default:
            return { key: 'job', label: 'Job' };
    }
}

function rankRow(row: JobPipelineKindRow): number {
    return (normalizeCount(row.running) * 1000)
        + (normalizeCount(row.queued) * 100)
        + (normalizeCount(row.failed) * 10)
        + normalizeCount(row.completed);
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

function lowercaseLeadingChar(value: string): string {
    if (!value) return value;
    return value.charAt(0).toLowerCase() + value.slice(1);
}

function resolveProgressUnit(job: JobProgressItem): string {
    if (job.kind === 'reclassify') return 'frames';
    return 'items';
}

function resolveSummarySubline(
    job: JobProgressItem,
    row: JobPipelineKindRow | null,
    analysisStatus: AnalysisStatus | null | undefined,
    t: JobsTranslateFn,
    kindLabel: (kind: string) => string
): string {
    const label = kindLabel(job.kind);
    if (supportsReclassifyQueueStatus(job.kind) && analysisStatus?.circuit_open) {
        return t('jobs.global_summary_circuit_open', { kind: label }, '{kind} paused by circuit breaker');
    }
    if (job.kind === 'model_download' && job.title.trim().length > 0) {
        return job.title;
    }
    const activityLabel = resolveActivityLabel(job, row, analysisStatus, t);
    return t(
        'jobs.global_summary_basic',
        { kind: label, activity: lowercaseLeadingChar(activityLabel) },
        '{kind} {activity}'
    );
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
        if (row?.throttledForLivePressure && job.current <= 0) {
            return t('jobs.activity_waiting_live_priority', undefined, 'Waiting for live detections');
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
    if (row && supportsReclassifyQueueStatus(row.kind) && analysisStatus?.circuit_open) {
        return t('jobs.blocker_circuit_open', undefined, 'Recent failures paused reclassification work');
    }
    if (row && supportsReclassifyQueueStatus(row.kind) && row.throttledForLivePressure) {
        return t('jobs.blocker_live_priority', undefined, 'Live detections have priority');
    }
    if (row && supportsReclassifyQueueStatus(row.kind) && row.throttledForMqttPressure) {
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
    const determinate = job.total > 0 && job.current > 0;
    const percent = determinate ? Math.min(100, Math.max(0, Math.round((job.current / job.total) * 100))) : null;
    const progressLabel = determinate
        ? formatProgress(job.current, job.total, resolveProgressUnit(job), t)
        : t('jobs.progress_working', undefined, 'Working...');
    const age = formatAge(Math.max(0, nowTs - job.updatedAt));
    const isStale = job.status === 'stale';
    const freshnessLabel = isStale
        ? t('jobs.freshness_stale', { age }, 'No update for {age}')
        : t('jobs.freshness_updated', { age }, 'Updated {age} ago');
    const blockerLabel = resolveBlockerLabel(row, analysisStatus, t);
    const detailLabel = isStale ? freshnessLabel : blockerLabel;

    return {
        activityLabel: resolveActivityLabel(job, row, analysisStatus, t),
        progressLabel,
        capacityLabel: resolveCapacityLabel(row, t),
        blockerLabel,
        detailLabel,
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
    const queueStatusApplies = supportsReclassifyQueueStatus(row.kind);
    const activityLabel = queueStatusApplies && analysisStatus?.circuit_open
        ? t('jobs.activity_circuit_open', undefined, 'Paused by circuit breaker')
        : row.running > 0
            ? t('jobs.activity_processing', undefined, 'Processing work')
            : t('jobs.activity_queued', undefined, 'Waiting in queue');

    return {
        activityLabel,
        capacityLabel: resolveCapacityLabel(row, t),
        blockerLabel: resolveBlockerLabel(row, analysisStatus, t),
        queueDepthLabel: row.queueDepthKnown
            ? t('jobs.queue_reported', undefined, 'Queue reported')
            : t('jobs.queue_depth_unknown', undefined, 'Queue depth not reported'),
        queueCapacityLabel: queueStatusApplies && normalizeCount(analysisStatus?.pending_capacity) > 0
            ? t('jobs.queue_slots_free', {
                available: normalizeCount(analysisStatus?.pending_available).toLocaleString(),
                capacity: normalizeCount(analysisStatus?.pending_capacity).toLocaleString()
            }, '{available} of {capacity} queue slots free')
            : null
    };
}

export function buildGlobalProgressSummary(
    activeJobs: JobProgressItem[],
    rowsByKind: Map<string, JobPipelineKindRow>,
    analysisStatus: AnalysisStatus | null | undefined,
    _nowTs: number,
    t: JobsTranslateFn,
    kindLabel: (kind: string) => string
): PresentedGlobalProgressSummary {
    if (activeJobs.length === 0) {
        return {
            headline: formatRunningHeadline(0, t),
            subline: t('jobs.activity_processing', undefined, 'Processing work'),
            progressLabel: t('jobs.progress_working', undefined, 'Working...'),
            determinate: false,
            percent: null
        };
    }

    const rankedRows = [...rowsByKind.values()].sort((a, b) => {
        const diff = rankRow(b) - rankRow(a);
        if (diff !== 0) return diff;
        return a.kind.localeCompare(b.kind);
    });
    const dominantKind = rankedRows[0]?.kind ?? activeJobs[0].kind;
    const dominantJob = activeJobs.find((job) => job.kind === dominantKind) ?? activeJobs[0];
    const dominantRow = rowsByKind.get(dominantKind) ?? null;
    const units = new Set(activeJobs.map((job) => resolveProgressUnit(job)));
    const compatible = units.size === 1 && activeJobs.every((job) => job.total > 0 && job.current > 0);
    let progressLabel = t('jobs.progress_working', undefined, 'Working...');
    let percent: number | null = null;

    if (compatible) {
        const total = activeJobs.reduce((sum, job) => sum + normalizeCount(job.total), 0);
        const current = activeJobs.reduce((sum, job) => sum + Math.min(normalizeCount(job.current), normalizeCount(job.total)), 0);
        const unit = resolveProgressUnit(activeJobs[0]);
        progressLabel = formatProgress(current, total, unit, t);
        percent = total > 0 ? Math.min(100, Math.max(0, Math.round((current / total) * 100))) : null;
    } else if (units.size > 1) {
        progressLabel = t(
            'jobs.global_summary_mixed_units',
            undefined,
            'Multiple jobs in progress'
        );
    }

    return {
        headline: formatRunningHeadline(activeJobs.length, t),
        subline: resolveSummarySubline(dominantJob, dominantRow, analysisStatus, t, kindLabel),
        progressLabel,
        determinate: compatible,
        percent
    };
}
