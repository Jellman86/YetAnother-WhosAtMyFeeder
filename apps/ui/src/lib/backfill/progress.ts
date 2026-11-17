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

export type TranslateCounts = (key: string, values: Record<string, number>) => string;

/**
 * How far a backfill has got, in words: how many Frigate events were checked, then what happened
 * to them. The count of added visits is left out for weather, which adds none. A finished job
 * never reads as still counting: with no total it says how many it checked, or that the range
 * held nothing.
 */
export function describeBackfillProgress(
    translate: TranslateCounts,
    processed: number,
    total: number,
    updated: number,
    skipped: number,
    errors: number,
    newDetections?: number,
    finished = false
): string {
    const checked = safeCount(processed);
    const of = safeCount(total) || (finished ? checked : 0);
    if (finished && of === 0) return translate('jobs.backfill_nothing_to_check', {});
    const counts = { updated: safeCount(updated), skipped: safeCount(skipped), errors: safeCount(errors) };
    const progress = of > 0
        ? translate('jobs.backfill_checked', { processed: checked, total: of })
        : translate('jobs.backfill_checked_so_far', { processed: checked });
    const outcome = newDetections === undefined
        ? translate('jobs.backfill_counts_weather', counts)
        : translate('jobs.backfill_counts_visits', { added: safeCount(newDetections), ...counts });
    return `${progress} · ${outcome}`;
}

/** What the server said about a finished job, beyond the counts the summary already gives. */
export type BackfillOutcomeNote =
    | { kind: 'known'; key: 'jobs.backfill_reason_nothing_in_range' | 'jobs.backfill_reason_weather_unavailable' }
    /** A reason this app has no words for, such as why rows were skipped: quoted as the server's. */
    | { kind: 'quoted'; message: string };

const KNOWN_OUTCOMES: Record<string, 'jobs.backfill_reason_nothing_in_range' | 'jobs.backfill_reason_weather_unavailable'> = {
    'no detections found in range': 'jobs.backfill_reason_nothing_in_range',
    'weather archive unavailable for range': 'jobs.backfill_reason_weather_unavailable',
};
/** Sentences that only repeat the counts: "Added 5 new detection(s)", "Updated 3 detection(s), 2 skipped". */
const COUNTS_ONLY = /^(?:added \d+ new detection\(s\)|no new detections found|updated \d+ detection\(s\))(?:, \d+ existing detection\(s\) improved)?(?:, \d+ skipped)?$/i;

export function backfillOutcomeNote(message: string | null | undefined): BackfillOutcomeNote | null {
    const said = normalizeMessage(message).replace(/[.\s]+$/, '');
    if (!said) return null;
    const key = KNOWN_OUTCOMES[said.toLowerCase()];
    if (key) return { kind: 'known', key };
    if (COUNTS_ONLY.test(said)) return null;
    return { kind: 'quoted', message: said };
}

/** A finished job's summary with the server's reason after it, when it gave one. */
export function withOutcomeNote(
    summary: string,
    message: string | null | undefined,
    say: (key: string, values?: Record<string, string>) => string
): string {
    const note = backfillOutcomeNote(message);
    if (!note) return summary;
    const text = note.kind === 'known' ? say(note.key) : say('jobs.backfill_server_note', { message: note.message });
    return `${summary} ${text}`;
}

/**
 * The older, English-only summary, still used by the Settings page. New callers use
 * `describeBackfillProgress`, which is worded in the reader's language.
 */
export function formatBackfillProgressSummary(
    processed: number,
    total: number,
    updated: number,
    skipped: number,
    errors: number,
    newDetections?: number
): string {
    const normalizedProcessed = safeCount(processed);
    const normalizedTotal = safeCount(total);
    const normalizedUpdated = safeCount(updated);
    const normalizedSkipped = safeCount(skipped);
    const normalizedErrors = safeCount(errors);
    const totalLabel = normalizedTotal > 0
        ? normalizedTotal.toLocaleString()
        : '?';

    const newLabel = newDetections === undefined ? '' : `${safeCount(newDetections).toLocaleString()} new • `;
    return `${normalizedProcessed.toLocaleString()}/${totalLabel} • ${newLabel}${normalizedUpdated.toLocaleString()} upd • ${normalizedSkipped.toLocaleString()} skip • ${normalizedErrors.toLocaleString()} err`;
}
