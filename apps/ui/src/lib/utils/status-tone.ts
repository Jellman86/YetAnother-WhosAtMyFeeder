import type { Tone } from '../components/ui/tone';

/**
 * One tone and one label for a reported system or job status (layout-patterns.md §1.3, §1.5).
 *
 * Work in flight needs nobody, so it takes the brand colour. Amber (`attention-*`) is kept for
 * a state a person should look at, rose for a failure and green (`success-*`) for healthy, in
 * every theme. A status we did not recognise or could not measure stays slate: it is never
 * rounded up to healthy.
 */

export type StatusTone = 'running' | 'attention' | 'failure' | 'healthy' | 'unknown';

const TONE_BY_STATUS: Readonly<Record<string, StatusTone>> = {
    running: 'running',
    processing: 'running',
    queued: 'running',
    recovering: 'running',
    elevated: 'running',
    warning: 'attention',
    degraded: 'attention',
    high: 'attention',
    critical: 'failure',
    error: 'failure',
    failing: 'failure',
    failed: 'failure',
    open: 'failure',
    ok: 'healthy',
    healthy: 'healthy',
    normal: 'healthy',
    idle: 'healthy',
    clear: 'healthy',
    resolved: 'healthy',
    recovered: 'healthy',
    connected: 'healthy',
    reachable: 'healthy',
    connecting: 'running',
    disconnected: 'attention',
    unreachable: 'attention',
    not_configured: 'attention',
    stopped: 'attention',
    unchecked: 'unknown',
    unknown: 'unknown'
};

/** Every status with a translated label under `jobs.status.<value>`. */
export const KNOWN_STATUSES: readonly string[] = Object.keys(TONE_BY_STATUS);

function normalise(value: string | null | undefined): string {
    return typeof value === 'string' ? value.trim().toLowerCase() : '';
}

export function statusTone(value: string | null | undefined): StatusTone {
    return TONE_BY_STATUS[normalise(value)] ?? 'unknown';
}

/**
 * The i18n key for a status, or null for a word the panel does not know. The caller shows
 * that word as its fallback, with the raw value in a title, rather than claiming a state.
 */
export function statusLabelKey(value: string | null | undefined): string | null {
    const status = normalise(value);
    if (status.length === 0) return 'jobs.status.unknown';
    return status in TONE_BY_STATUS ? `jobs.status.${status}` : null;
}

/** The design system's tone for a status: StatusChip and StateBlock draw it, always with its words. */
export const STATUS_TONE: Readonly<Record<StatusTone, Tone>> = {
    running: 'info',
    attention: 'attention',
    failure: 'fail',
    healthy: 'ok',
    unknown: 'neutral'
};

/** The verdict card, which takes the tone as a whole: its soft ground and its edge. */
export const STATUS_SURFACE: Readonly<Record<StatusTone, string>> = {
    running: 'border-status-info-line bg-status-info-soft',
    attention: 'border-status-attention-line bg-status-attention-soft',
    failure: 'border-status-fail-line bg-status-fail-soft',
    healthy: 'border-status-ok-line bg-status-ok-soft',
    unknown: 'border-line-soft bg-surface-sunken'
};
