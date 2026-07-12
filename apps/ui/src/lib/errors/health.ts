export interface VideoClassifierCardState {
    status: string;
    summary: string;
    pending: number;
    active: number;
    failureCount: number;
    openUntil: string;
}

function asNumber(value: unknown): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
}

function asText(value: unknown, fallback = ''): string {
    if (typeof value !== 'string') return fallback;
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : fallback;
}

function normalizeStatus(value: unknown): string {
    const normalized = asText(value).toLowerCase();
    return normalized;
}

function asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

export interface FrigateMediaAdvisory {
    /** True when Frigate media unavailability is common enough to warrant showing guidance. */
    elevated: boolean;
    /** Fraction (0..1) of started events dropped because Frigate had no snapshot/media. */
    rate: number;
    /** Count of events dropped for snapshot/media unavailability. */
    dropped: number;
    /** Number of events the pipeline has started (the sample size). */
    started: number;
}

// The ingest-pipeline drop reasons that mean "Frigate had no snapshot/media when we needed it".
// These are the transient-object / retention cases the Event-Not-Found guide addresses — not
// config-driven filter drops (which are informational and expected).
const FRIGATE_MEDIA_DROP_REASONS = ['classify_snapshot_unavailable', 'classify_snapshot_timeout'];

// Only advise once there is a meaningful sample and a materially elevated rate, so a couple of
// early misses on a fresh install never nag the user.
const ADVISORY_MIN_STARTED = 20;
const ADVISORY_MIN_DROPPED = 5;
const ADVISORY_MIN_RATE = 0.15;

/**
 * Decide whether to surface in-app "Event Not Found" guidance, based on how often the ingest
 * pipeline has dropped detections because Frigate had no snapshot/media for them.
 */
export function getFrigateMediaAdvisory(
    health: Record<string, unknown> | null | undefined
): FrigateMediaAdvisory {
    const pipeline = asRecord(health?.event_pipeline);
    const dropReasons = asRecord(pipeline.drop_reasons);
    const dropped = FRIGATE_MEDIA_DROP_REASONS.reduce((sum, reason) => sum + asNumber(dropReasons[reason]), 0);
    const started = asNumber(pipeline.started_events);
    const rate = started > 0 ? dropped / started : 0;
    const elevated = started >= ADVISORY_MIN_STARTED && dropped >= ADVISORY_MIN_DROPPED && rate >= ADVISORY_MIN_RATE;
    return { elevated, rate, dropped, started };
}

export function getVideoClassifierCardState(
    health: Record<string, unknown> | null | undefined
): VideoClassifierCardState {
    const video = asRecord(health?.video_classifier);
    const pending = asNumber(video.pending);
    const active = asNumber(video.active);
    const failureCount = asNumber(video.failure_count);
    const circuitOpen = Boolean(video.circuit_open);
    const explicitStatus = normalizeStatus(video.status);

    let status = explicitStatus;
    if (circuitOpen) {
        status = 'open';
    } else if (!status || status === 'unknown') {
        if (active > 0) {
            status = 'processing';
        } else if (pending > 0) {
            status = 'queued';
        } else {
            status = 'idle';
        }
    }

    const openUntil = asText(video.open_until, 'Closed') || 'Closed';
    const summary = circuitOpen
        ? `Video circuit breaker is open with ${failureCount.toLocaleString()} recent failures.`
        : `${pending.toLocaleString()} queued, ${active.toLocaleString()} active video jobs.`;

    return {
        status,
        summary,
        pending,
        active,
        failureCount,
        openUntil,
    };
}
