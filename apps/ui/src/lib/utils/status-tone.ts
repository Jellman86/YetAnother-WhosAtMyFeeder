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

/** A pill or a subsystem card: edge, fill and text. */
export const STATUS_PILL: Readonly<Record<StatusTone, string>> = {
    running: 'border-brand-200/80 bg-brand-50 text-brand-700 dark:border-brand-800/60 dark:bg-brand-900/30 dark:text-brand-300',
    attention: 'border-attention-200/80 bg-attention-50 text-attention-800 dark:border-attention-800/60 dark:bg-attention-950/30 dark:text-attention-200',
    failure: 'border-rose-200/80 bg-rose-50 text-rose-700 dark:border-rose-800/60 dark:bg-rose-950/30 dark:text-rose-200',
    healthy: 'border-success-200/80 bg-success-50 text-success-700 dark:border-success-800/60 dark:bg-success-950/30 dark:text-success-200',
    unknown: 'border-slate-200/80 bg-slate-50 text-slate-700 dark:border-slate-700/60 dark:bg-slate-900/50 dark:text-slate-200'
};

/** The verdict card, which takes the colour as a whole rather than a pill on neutral ground. */
export const STATUS_SURFACE: Readonly<Record<StatusTone, string>> = {
    running: 'border-brand-200/80 bg-brand-50/70 dark:border-brand-800/50 dark:bg-brand-950/30',
    attention: 'border-attention-200/80 bg-attention-50/70 dark:border-attention-800/50 dark:bg-attention-950/30',
    failure: 'border-rose-200/80 bg-rose-50/70 dark:border-rose-800/50 dark:bg-rose-950/30',
    healthy: 'border-success-200/80 bg-success-50/70 dark:border-success-800/50 dark:bg-success-950/30',
    unknown: 'border-slate-200/80 bg-slate-50/70 dark:border-slate-700/60 dark:bg-slate-900/60'
};
