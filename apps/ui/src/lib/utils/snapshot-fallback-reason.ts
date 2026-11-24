export const SNAPSHOT_FALLBACK_REASON_KEYS = [
    'clip_not_retained',
    'clip_unavailable',
    'clip_invalid',
    'clip_decode_failed',
    'clip_fetch_failed',
    'event_not_found',
    'video_no_results',
    'below_threshold',
    'video_no_usable_result',
    'frigate_not_ready',
    'event_timeout',
    'event_request_error',
    'event_unknown_error',
    'clip_not_found',
    'clip_timeout',
    'clip_request_error',
    'clip_unknown_error',
    'video_timeout',
    'video_worker_native_runtime_quarantined',
    'video_worker_circuit_open',
    'video_worker_heartbeat_timeout',
    'video_worker_deadline_exceeded',
    'video_worker_startup_timeout',
    'video_worker_unavailable',
    'invalid_score',
    'abstention_label',
    'non_bird',
    'blocked_label',
    'low_confidence',
    'out_of_range'
] as const;

const KNOWN_REASON_KEYS = new Set<string>(SNAPSHOT_FALLBACK_REASON_KEYS);

export type FallbackTranslate = (
    key: string,
    options?: { default?: string; values?: Record<string, string | number> }
) => string;

/**
 * Translate a video-analysis snapshot fallback reason code without leaking raw snake_case tokens.
 * Handles both finite reason codes and dynamic `event_http_<status>` / `clip_http_<status>` codes.
 */
export function formatSnapshotFallbackReason(
    code: string | null | undefined,
    t: FallbackTranslate,
    genericFallback?: string
): string {
    const fallback =
        genericFallback ??
        t('detection.reclassification.snapshot_fallback_reason_generic', {
            default: 'Video clip was unavailable'
        });
    const trimmed = (code ?? '').trim();
    if (!trimmed) return fallback;

    const eventHttp = /^event_http_(\d{3})$/.exec(trimmed);
    if (eventHttp) {
        return t('detection.reclassification.snapshot_fallback_reason.event_http', {
            values: { status: eventHttp[1] },
            default: 'Frigate refused the request for this event (status {status}). Check Frigate and try again.'
        });
    }

    const clipHttp = /^clip_http_(\d{3})$/.exec(trimmed);
    if (clipHttp) {
        return t('detection.reclassification.snapshot_fallback_reason.clip_http', {
            values: { status: clipHttp[1] },
            default: 'Frigate refused the request for the video clip (status {status}). Check Frigate and try again.'
        });
    }

    if (KNOWN_REASON_KEYS.has(trimmed)) {
        return t(`detection.reclassification.snapshot_fallback_reason.${trimmed}`, {
            default: fallback
        });
    }

    return fallback;
}
