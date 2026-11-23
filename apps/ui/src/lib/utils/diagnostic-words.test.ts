import { describe, expect, it } from 'vitest';
import { diagnosticWordsKey } from './diagnostic-words';
import enJobs from '../i18n/locales/en/jobs.json';

describe('diagnosticWordsKey', () => {
    it('words a known backend reason code instead of showing its raw message', () => {
        expect(diagnosticWordsKey('drop_classify_snapshot_timeout')).toBe('classify_snapshot_timeout');
        expect(diagnosticWordsKey('drop_classify_snapshot_overloaded')).toBe('classify_snapshot_overloaded');
        expect(diagnosticWordsKey('drop_save_and_notify_failed')).toBe('save_and_notify_failed');
        expect(diagnosticWordsKey('stale_job')).toBe('stale_job');
        expect(diagnosticWordsKey(' DROP_CLASSIFIER_EMPTY_RESULTS ')).toBe('classifier_empty_results');
    });

    it('words a failed or timed-out pipeline stage, whose message carries the raw exception', () => {
        // "Stage classify failed: {exception}" can hold paths and URLs; the page never leads with it.
        expect(diagnosticWordsKey('stage_failure')).toBe('stage_failure');
        expect(diagnosticWordsKey('stage_timeout')).toBe('stage_timeout');
    });

    it('maps every routine and fault backend diagnostic code to a worded English entry', () => {
        const samples = [
            'classify_snapshot_lease_expired',
            'drop_live_event_stale',
            'drop_live_event_coalesced',
            'drop_end_recovery_lookup_failed',
            'drop_update_recovery_lookup_failed',
            'drop_update_recovery_cooldown',
            'drop_false_positive_tombstone_active',
            'drop_nest_mode_dedupe',
            'frigate_missing_marked',
            'frigate_missing_deleted',
            'frigate_missing_kept',
            'frigate_went_offline',
            'video_circuit_opened',
            'video_circuit_open',
            'video_queue_full',
            'video_timeout',
            'video_cancelled',
            'video_exception',
            'video_photo_update',
            'auto_classify_retry_after_worker_failure',
            'clip_unavailable',
            'clip_not_found',
            'event_not_found',
            'snapshot_unavailable',
            'maintenance_deprioritized',
            'maintenance_starved',
            'throttled_by_live_pressure',
            'job_failed',
            'exception',
            'job_timeout',
            'timeout',
            'fetch_snapshot_failed',
            'snapshot_cache_failed',
            'rfdetr_cpu_fallback',
            'native_crop_crash',
            'crop_worker_retired',
            'crop_cleanup_unconfirmed',
            'native_cpu_recovery_active',
            'circuit_open',
            'recovery_active',
            'hardware_decode_fallback_frequent',
            'hardware_decode_fallback_repeated',
            'hardware_decode_decode_failed',
            'retention_paused_daily_totals',
            'queue_full',
            'queue_full_race',
            'loop_reset_drop'
        ];
        const words = enJobs.diagnostic_words as Record<string, { title?: string; next?: string }>;
        for (const code of samples) {
            const key = diagnosticWordsKey(code);
            expect(key, `expected ${code} to resolve to a specific key`).not.toBe('generic');
            expect(words[key]?.title?.trim().length ?? 0, `missing English title for ${key}`).toBeGreaterThan(0);
            expect(words[key]?.next?.trim().length ?? 0, `missing English next step for ${key}`).toBeGreaterThan(0);
        }
    });

    it('gives any other code a generic cause, never the raw message as its title', () => {
        expect(diagnosticWordsKey('drop_something_new')).toBe('generic');
        expect(diagnosticWordsKey('refresh_failed')).toBe('generic');
        expect(diagnosticWordsKey('')).toBe('generic');
        expect(diagnosticWordsKey(null)).toBe('generic');
    });
});
