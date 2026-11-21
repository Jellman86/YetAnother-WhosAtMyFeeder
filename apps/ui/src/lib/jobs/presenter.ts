import type { AnalysisStatus } from '../api/maintenance';
import type { JobProgressItem } from '../stores/job_progress.svelte';
import type { JobPipelineKindRow } from './pipeline';

type JobsTranslationValues = Record<string, string | number | boolean | Date | null | undefined>;
export type JobsTranslateFn = (key: string, values?: JobsTranslationValues, fallback?: string) => string;

export interface PresentedPipelineKindRow {
    activityLabel: string;
    capacityLabel: string | null;
    blockerLabel: string | null;
    queueDepthLabel: string;
    queueCapacityLabel: string | null;
}

export interface PresentedWorkLane {
    title: string;
    stateLabel: string;
    runningLabel: string;
    queuedLabel: string;
    capacityLabel: string | null;
    blockerLabel: string | null;
    batchLabel: string | null;
    candidateLabel: string | null;
    freshnessLabel: string | null;
}

export interface PresentedGlobalProgressSummary {
    headline: string;
    subline: string;
    /** Measured progress in words, or null when there is no common total to measure against. */
    progressLabel: string | null;
    determinate: boolean;
    percent: number | null;
}

const DEFAULT_ANALYZE_UNKNOWN_BATCH_LIMIT = 50;
const DEFAULT_ANALYZE_UNKNOWN_SCAN_LIMIT = 200;

function formatRunningHeadline(count: number, t: JobsTranslateFn): string {
    if (count === 1) {
        return t('jobs.global_running_single', undefined, '1 job running');
    }
    return t('jobs.global_running_multi', { count }, '{count, plural, one {# job running} other {# jobs running}}');
}

/**
 * Every active job counted once, by the state it reports: running, queued, or stopped reporting.
 * A queued or silent job is never called running, and the counts add up to the total shown.
 */
function formatActiveHeadline(activeJobs: JobProgressItem[], t: JobsTranslateFn): string {
    const queued = activeJobs.filter((job) => job.status === 'queued').length;
    const stale = activeJobs.filter((job) => job.status === 'stale').length;
    return formatCountsHeadline(activeJobs.length - queued - stale, queued, stale, t);
}

function formatCountsHeadline(running: number, queued: number, stale: number, t: JobsTranslateFn): string {
    const total = running + queued + stale;
    if (queued === 0 && stale === 0) return formatRunningHeadline(running, t);
    if (running === 0 && stale === 0) {
        return t('jobs.global_queued_only', { count: queued }, '{count, plural, one {# job queued} other {# jobs queued}}');
    }
    if (running === 0 && queued === 0) {
        return t('jobs.global_not_responding', { count: stale.toLocaleString() }, '{count} not responding');
    }
    const parts = [
        running > 0 ? t('jobs.lane_running_count', { count: running.toLocaleString() }, '{count} running') : null,
        queued > 0 ? t('jobs.lane_queued_count', { count: queued.toLocaleString() }, '{count} queued') : null,
        stale > 0 ? t('jobs.global_not_responding', { count: stale.toLocaleString() }, '{count} not responding') : null
    ].filter((part): part is string => part !== null);
    return t(
        'jobs.global_breakdown',
        { count: total, parts: parts.join(', ') },
        '{count, plural, one {# job} other {# jobs}}: {parts}'
    );
}

function supportsReclassifyQueueStatus(kind: string): boolean {
    return kind === 'reclassify' || kind === 'reclassify_batch';
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
    if (typeof job.unit === 'string' && job.unit.trim().length > 0) return job.unit.trim();
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
        return t('jobs.global_summary_circuit_open', { kind: label }, '{kind} paused after repeated failures');
    }
    if (job.kind === 'model_download' && job.title.trim().length > 0) {
        return job.title;
    }
    const activityLabel = resolveActivityLabel(job, row, analysisStatus, t);
    return t(
        'jobs.global_summary_activity',
        { kind: label, activity: lowercaseLeadingChar(activityLabel) },
        '{kind}: {activity}'
    );
}

function resolveActivityLabel(
    job: JobProgressItem,
    row: JobPipelineKindRow | null,
    analysisStatus: AnalysisStatus | null | undefined,
    t: JobsTranslateFn
): string {
    if (job.phase === 'waiting_for_frigate') {
        return t('jobs.activity_waiting_for_frigate', undefined, 'Waiting for Frigate to answer');
    }
    if (job.phase === 'waiting') {
        return t('jobs.activity_waiting', undefined, 'Waiting for a worker');
    }
    if (job.phase === 'selecting_best_frame') {
        return t('jobs.activity_selecting_best_frame', undefined, 'Choosing the best-quality frame');
    }
    if (job.phase === 'fetching_media') {
        return t('jobs.activity_fetching_media', undefined, 'Fetching retained media');
    }
    if (job.phase === 'analyzing') {
        return t('jobs.activity_reclassify_running', undefined, 'Analysing clips');
    }
    if (job.kind === 'reclassify') {
        if (analysisStatus?.circuit_open) {
            return t('jobs.activity_circuit_open', undefined, 'Paused after repeated failures');
        }
        if (row?.throttledForLivePressure && job.current <= 0) {
            return t('jobs.activity_waiting_live_priority', undefined, 'Waiting while new visits are named');
        }
        if (row?.throttledForMqttPressure && job.current <= 0) {
            return t('jobs.activity_waiting_slots', undefined, 'Waiting for the model to be free');
        }
        return t('jobs.activity_reclassify_running', undefined, 'Analysing clips');
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

function resolveLaneCapacity(row: JobPipelineKindRow | null, t: JobsTranslateFn): string | null {
    if (!row) return null;
    const running = normalizeCount(row.running);
    const effective = normalizeCount(row.maxConcurrentEffective);
    const configured = normalizeCount(row.maxConcurrentConfigured);
    const capacity = effective > 0 ? effective : configured;
    if (capacity > 0) {
        return t('jobs.capacity_worker_slots', {
            running: running.toLocaleString(),
            capacity: capacity.toLocaleString()
        }, '{running} of {capacity} worker slots busy');
    }
    return null;
}

function resolveLaneTitle(row: JobPipelineKindRow, t: JobsTranslateFn, kindLabel: (kind: string) => string): string {
    // Both reclassify kinds read the same queue telemetry, but they are not the same work:
    // titling both "Analyze Unknowns" showed one job twice under one name.
    if (row.kind === 'reclassify') {
        return t('jobs.work_lane_analyze_unknowns', undefined, 'Naming Unknown bird visits');
    }
    return kindLabel(row.kind);
}

function resolveBatchLabel(analysisStatus: AnalysisStatus | null | undefined, t: JobsTranslateFn): string {
    const queueLimit = normalizeCount(analysisStatus?.queue_limit) || DEFAULT_ANALYZE_UNKNOWN_BATCH_LIMIT;
    const scanLimit = normalizeCount(analysisStatus?.scan_limit) || DEFAULT_ANALYZE_UNKNOWN_SCAN_LIMIT;
    return t('jobs.analyze_unknowns_batch_label', {
        queueLimit: queueLimit.toLocaleString(),
        scanLimit: scanLimit.toLocaleString()
    }, 'Up to {queueLimit} at a time, from the newest {scanLimit}');
}

function resolveCandidateLabel(analysisStatus: AnalysisStatus | null | undefined, t: JobsTranslateFn): string | null {
    const remaining = normalizeCount(analysisStatus?.remaining_candidates);
    if (remaining > 0) {
        return t('jobs.analyze_unknowns_candidates_remain', {
            count: remaining.toLocaleString()
        }, '{count} more may remain');
    }
    if (analysisStatus?.scan_truncated) {
        return t('jobs.analyze_unknowns_scan_truncated', undefined, 'More may remain');
    }
    return null;
}

function resolveLaneStateLabel(
    row: JobPipelineKindRow,
    analysisStatus: AnalysisStatus | null | undefined,
    t: JobsTranslateFn
): string {
    if (supportsReclassifyQueueStatus(row.kind) && analysisStatus?.circuit_open) {
        return t('jobs.state_paused', undefined, 'Paused');
    }
    if (row.running > 0) {
        return t('jobs.state_running', undefined, 'Running');
    }
    if (normalizeCount(row.queued) > 0 || !row.queueDepthKnown) {
        return t('jobs.state_queued', undefined, 'Queued');
    }
    return t('jobs.state_idle', undefined, 'Idle');
}

function formatLaneCounts(row: JobPipelineKindRow, t: JobsTranslateFn): { runningLabel: string; queuedLabel: string } {
    const running = normalizeCount(row.running);
    const queued = normalizeCount(row.queued);
    return {
        runningLabel: t('jobs.lane_running_count', { count: running.toLocaleString() }, '{count} running'),
        queuedLabel: row.queueDepthKnown
            ? t('jobs.lane_queued_count', { count: queued.toLocaleString() }, '{count} queued')
            : t('jobs.queue_depth_unknown', undefined, 'Queue depth not reported')
    };
}

function formatLaneSummarySubline(row: JobPipelineKindRow, t: JobsTranslateFn): string {
    const counts = formatLaneCounts(row, t);
    return [counts.runningLabel, counts.queuedLabel].join(' · ');
}

function resolveBlockerLabel(
    row: JobPipelineKindRow | null,
    analysisStatus: AnalysisStatus | null | undefined,
    t: JobsTranslateFn
): string | null {
    if (row && supportsReclassifyQueueStatus(row.kind) && analysisStatus?.circuit_open) {
        return t('jobs.blocker_circuit_open', undefined, 'Repeated failures paused the analysis');
    }
    if (row && supportsReclassifyQueueStatus(row.kind) && row.throttledForLivePressure) {
        return t('jobs.blocker_live_priority', undefined, 'New visits are named first');
    }
    if (row && supportsReclassifyQueueStatus(row.kind) && row.throttledForMqttPressure) {
        return t('jobs.blocker_mqtt_pressure', undefined, 'Background work is slowed while camera events are busy');
    }
    return null;
}

export function presentPipelineKindRow(
    row: JobPipelineKindRow,
    analysisStatus: AnalysisStatus | null | undefined,
    t: JobsTranslateFn
): PresentedPipelineKindRow {
    const queueStatusApplies = supportsReclassifyQueueStatus(row.kind);
    const activityLabel = queueStatusApplies && analysisStatus?.circuit_open
        ? t('jobs.activity_circuit_open', undefined, 'Paused after repeated failures')
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

export function presentWorkLane(
    row: JobPipelineKindRow,
    analysisStatus: AnalysisStatus | null | undefined,
    nowTs: number,
    t: JobsTranslateFn,
    kindLabel: (kind: string) => string
): PresentedWorkLane {
    const queueStatusApplies = supportsReclassifyQueueStatus(row.kind);
    const counts = formatLaneCounts(row, t);
    const age = row.queueUpdatedAt !== null
        ? formatAge(Math.max(0, nowTs - row.queueUpdatedAt))
        : null;

    return {
        title: resolveLaneTitle(row, t, kindLabel),
        stateLabel: resolveLaneStateLabel(row, analysisStatus, t),
        runningLabel: counts.runningLabel,
        queuedLabel: counts.queuedLabel,
        capacityLabel: resolveLaneCapacity(row, t),
        blockerLabel: resolveBlockerLabel(row, analysisStatus, t),
        batchLabel: queueStatusApplies ? resolveBatchLabel(analysisStatus, t) : null,
        candidateLabel: queueStatusApplies ? resolveCandidateLabel(analysisStatus, t) : null,
        freshnessLabel: age ? t('jobs.queue_updated_age', { age }, 'Queue read {age} ago') : null
    };
}

/**
 * The server's own count of its prominent work (`jobs_summary` in the pushed status), with the work
 * only this browser follows. The snapshot lists at most a hundred jobs while its lanes count every
 * one, so counting the listed jobs would put "100 queued" above a lane saying "151 queued".
 */
export interface ServerJobCounts {
    running: number;
    queued: number;
    progress: { current: number; total: number; unit: string } | null;
    browserOnly: JobProgressItem[];
}

export function buildGlobalProgressSummary(
    activeJobs: JobProgressItem[],
    rowsByKind: Map<string, JobPipelineKindRow>,
    analysisStatus: AnalysisStatus | null | undefined,
    _nowTs: number,
    t: JobsTranslateFn,
    kindLabel: (kind: string) => string,
    server?: ServerJobCounts
): PresentedGlobalProgressSummary {
    const serverTotal = server ? server.running + server.queued + server.browserOnly.length : activeJobs.length;
    if (activeJobs.length === 0 || serverTotal === 0) {
        const dominantRow = [...rowsByKind.values()].sort((a, b) => {
            const diff = rankRow(b) - rankRow(a);
            if (diff !== 0) return diff;
            return a.kind.localeCompare(b.kind);
        })[0];
        if (dominantRow) {
            const lane = presentWorkLane(dominantRow, analysisStatus, _nowTs, t, kindLabel);
            return {
                headline: t('jobs.global_queue_only_headline', {
                    title: lane.title,
                    state: lowercaseLeadingChar(lane.stateLabel)
                }, '{title}: {state}'),
                subline: formatLaneSummarySubline(dominantRow, t),
                progressLabel: lane.blockerLabel ?? lane.batchLabel ?? lane.freshnessLabel,
                determinate: false,
                percent: null
            };
        }
        return {
            headline: formatRunningHeadline(0, t),
            subline: t('jobs.activity_processing', undefined, 'Processing work'),
            progressLabel: null,
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
    const kinds = new Set(activeJobs.map((job) => job.kind));
    const compatible = units.size === 1 && kinds.size === 1 && activeJobs.every((job) => job.total > 0 && job.current >= 0);
    // Jobs with different units or kinds have no common total, so no bar or figure is drawn for them.
    let progressLabel: string | null = null;
    let percent: number | null = null;

    if (compatible) {
        const total = activeJobs.reduce((sum, job) => sum + normalizeCount(job.total), 0);
        const current = activeJobs.reduce((sum, job) => sum + Math.min(normalizeCount(job.current), normalizeCount(job.total)), 0);
        const unit = resolveProgressUnit(activeJobs[0]);
        progressLabel = formatProgress(current, total, unit, t);
        percent = total > 0 ? Math.min(100, Math.max(0, Math.round((current / total) * 100))) : null;
    }

    if (server) {
        const local = server.browserOnly;
        const localQueued = local.filter((job) => job.status === 'queued').length;
        const localStale = local.filter((job) => job.status === 'stale').length;
        const headline = formatCountsHeadline(
            server.running + local.length - localQueued - localStale,
            server.queued + localQueued,
            localStale,
            t
        );
        // A bar only for work that shares one total: the server's alone, or the browser's alone.
        const serverProgress = local.length === 0 ? server.progress : null;
        const onlyLocal = server.running + server.queued === 0;
        const progress = serverProgress
            ? {
                  label: formatProgress(serverProgress.current, serverProgress.total, serverProgress.unit, t),
                  percent: Math.min(100, Math.max(0, Math.round((serverProgress.current / serverProgress.total) * 100)))
              }
            : onlyLocal && compatible
                ? { label: progressLabel, percent }
                : null;
        return {
            headline,
            subline: resolveSummarySubline(dominantJob, dominantRow, analysisStatus, t, kindLabel),
            progressLabel: progress?.label ?? null,
            determinate: progress !== null,
            percent: progress?.percent ?? null
        };
    }

    return {
        headline: formatActiveHeadline(activeJobs, t),
        subline: resolveSummarySubline(dominantJob, dominantRow, analysisStatus, t, kindLabel),
        progressLabel,
        determinate: compatible,
        percent
    };
}
