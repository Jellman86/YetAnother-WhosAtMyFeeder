/**
 * Backend diagnostics carry a reason code and an English message written for logs ("Dropped event
 * due to classify_snapshot_timeout", "Stage classify failed: <exception>"). The message can hold an
 * exception's text, paths and URLs, so Health never leads with it: every known backend code gets a
 * plain-language title and next step under `jobs.diagnostic_words.<key>.title` and `.next`, every
 * genuinely unrecognised code gets the generic one, and the backend's (redacted) message stays
 * under Technical details.
 */
const WORDED = new Set([
    'classify_snapshot_timeout',
    'classify_snapshot_overloaded',
    'classify_snapshot_unavailable',
    'classify_snapshot_lease_expired',
    'classifier_empty_results',
    'save_and_notify_failed',
    'stage_failure',
    'stage_timeout',
    'live_event_stale',
    'live_event_coalesced',
    'recovery_lookup_failed',
    'update_recovery_cooldown',
    'false_positive_ignored',
    'nest_mode_dedupe',
    'frigate_missing_marked',
    'frigate_missing_deleted',
    'frigate_missing_kept',
    'frigate_went_offline',
    'video_circuit_open',
    'video_queue_full',
    'video_timeout',
    'video_cancelled',
    'video_exception',
    'video_photo_update',
    'video_retry_after_worker_failure',
    'clip_unavailable',
    'maintenance_held_back',
    'stale_job',
    'job_failed',
    'job_timeout',
    'fetch_snapshot_failed',
    'snapshot_cache_failed',
    'rfdetr_cpu_fallback',
    'bird_finder_worker_crash',
    'native_cpu_recovery',
    'worker_circuit_open',
    'worker_recovering',
    'hardware_decode_fallback',
    'retention_paused_daily_totals',
    'notification_queue_full',
    'notification_loop_reset'
]);

const ALIASES: Record<string, string> = {
    end_recovery_lookup_failed: 'recovery_lookup_failed',
    update_recovery_lookup_failed: 'recovery_lookup_failed',
    false_positive_tombstone_active: 'false_positive_ignored',
    video_circuit_opened: 'video_circuit_open',
    auto_classify_retry_after_worker_failure: 'video_retry_after_worker_failure',
    clip_not_found: 'clip_unavailable',
    event_not_found: 'clip_unavailable',
    snapshot_unavailable: 'clip_unavailable',
    maintenance_deprioritized: 'maintenance_held_back',
    maintenance_starved: 'maintenance_held_back',
    throttled_by_live_pressure: 'maintenance_held_back',
    exception: 'job_failed',
    timeout: 'job_timeout',
    native_crop_crash: 'bird_finder_worker_crash',
    crop_worker_retired: 'bird_finder_worker_crash',
    crop_cleanup_unconfirmed: 'bird_finder_worker_crash',
    circuit_open: 'worker_circuit_open',
    recovery_active: 'worker_recovering',
    queue_full: 'notification_queue_full',
    queue_full_race: 'notification_queue_full',
    loop_reset_drop: 'notification_loop_reset'
};

export function diagnosticWordsKey(reasonCode: string | null | undefined): string {
    const code = (reasonCode ?? '').trim().toLowerCase();
    const key = code.startsWith('drop_') ? code.slice('drop_'.length) : code;
    if (WORDED.has(key)) return key;
    if (key in ALIASES) return ALIASES[key];
    if (key.startsWith('hardware_decode_')) return 'hardware_decode_fallback';
    if (key.startsWith('native_cpu_recovery_')) return 'native_cpu_recovery';
    return 'generic';
}
