/**
 * Why a favourite's own copy (#178) could not be saved, read from the code the archive worker
 * stored (`backend/app/services/archive_service.py`), so the record can say what was not kept,
 * the cause and the next step instead of a bare "Archive failed".
 */
export type ArchiveLoss = 'both' | 'photo' | 'clip';

export type ArchiveFailureCause =
    | 'frigate_unreachable'
    | 'frigate_timeout'
    | 'frigate_refused'
    | 'frigate_error'
    | 'clip_cut_short'
    | 'disk_full'
    | 'disk_error'
    | 'unknown';

export interface ArchiveFailureInput {
    error?: string | null;
    snapshot_state?: string | null;
    clip_state?: string | null;
    retry_at?: string | null;
}

export interface ArchiveFailureExplanation {
    lost: ArchiveLoss;
    cause: ArchiveFailureCause;
    /** When the worker tries again by itself, or null once its attempts are spent. */
    retryAt: number | null;
}

function lostAssets(snapshot: string | null | undefined, clip: string | null | undefined): ArchiveLoss {
    const photoFailed = snapshot === 'failed';
    const clipFailed = clip === 'failed';
    if (photoFailed && !clipFailed) return 'photo';
    if (clipFailed && !photoFailed) return 'clip';
    return 'both';
}

function causeOf(error: string | null | undefined): ArchiveFailureCause {
    const code = (error ?? '').trim().toLowerCase();
    if (code === 'disk_full') return 'disk_full';
    if (code === 'disk_error') return 'disk_error';
    if (code === 'clip_partial') return 'clip_cut_short';
    if (code.endsWith('_request_error')) return 'frigate_unreachable';
    if (code.endsWith('_timeout')) return 'frigate_timeout';
    const http = /_http_(\d{3})$/.exec(code);
    if (http) return http[1] === '401' || http[1] === '403' ? 'frigate_refused' : 'frigate_error';
    return 'unknown';
}

export function explainArchiveFailure(status: ArchiveFailureInput): ArchiveFailureExplanation {
    const retry = status.retry_at ? Date.parse(status.retry_at) : Number.NaN;
    return {
        lost: lostAssets(status.snapshot_state, status.clip_state),
        cause: causeOf(status.error),
        retryAt: Number.isFinite(retry) ? retry : null
    };
}
