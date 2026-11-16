import { describe, expect, it } from 'vitest';
import { explainArchiveFailure } from './archive-failure';

describe('explainArchiveFailure', () => {
    it('says what was not kept, from the per-asset states', () => {
        expect(explainArchiveFailure({ error: 'snapshot_timeout', snapshot_state: 'failed', clip_state: 'failed' }).lost).toBe('both');
        expect(explainArchiveFailure({ error: 'snapshot_timeout', snapshot_state: 'failed', clip_state: 'durable' }).lost).toBe('photo');
        expect(explainArchiveFailure({ error: 'clip_timeout', snapshot_state: 'durable', clip_state: 'failed' }).lost).toBe('clip');
        // Without per-asset states the copy as a whole is what failed.
        expect(explainArchiveFailure({ error: null }).lost).toBe('both');
    });

    it('reads the cause from the code the archive worker stored', () => {
        expect(explainArchiveFailure({ error: 'snapshot_request_error' }).cause).toBe('frigate_unreachable');
        expect(explainArchiveFailure({ error: 'clip_request_error' }).cause).toBe('frigate_unreachable');
        expect(explainArchiveFailure({ error: 'snapshot_timeout' }).cause).toBe('frigate_timeout');
        expect(explainArchiveFailure({ error: 'clip_timeout' }).cause).toBe('frigate_timeout');
        expect(explainArchiveFailure({ error: 'snapshot_http_500' }).cause).toBe('frigate_error');
        expect(explainArchiveFailure({ error: 'clip_http_401' }).cause).toBe('frigate_refused');
        expect(explainArchiveFailure({ error: 'clip_http_403' }).cause).toBe('frigate_refused');
        expect(explainArchiveFailure({ error: 'clip_partial' }).cause).toBe('clip_cut_short');
        expect(explainArchiveFailure({ error: 'disk_full' }).cause).toBe('disk_full');
        expect(explainArchiveFailure({ error: 'disk_error' }).cause).toBe('disk_error');
    });

    it('does not invent a cause it was not given', () => {
        expect(explainArchiveFailure({ error: null }).cause).toBe('unknown');
        expect(explainArchiveFailure({ error: 'snapshot_unknown_error' }).cause).toBe('unknown');
        expect(explainArchiveFailure({ error: 'something_new' }).cause).toBe('unknown');
    });

    it('says whether it will be tried again by itself, and when', () => {
        const retry = explainArchiveFailure({ error: 'disk_full', retry_at: '2026-11-15T14:05:00Z' });
        expect(retry.retryAt).toBe(Date.parse('2026-11-15T14:05:00Z'));
        expect(explainArchiveFailure({ error: 'disk_full', retry_at: null }).retryAt).toBeNull();
        expect(explainArchiveFailure({ error: 'disk_full', retry_at: 'not a time' }).retryAt).toBeNull();
    });

    it('does not name a retry time that has already passed: the retry is due, not scheduled', () => {
        const now = Date.parse('2026-11-15T14:10:00Z');
        const due = explainArchiveFailure({ error: 'disk_full', retry_at: '2026-11-15T14:05:00Z' }, now);
        expect(due.retryDue).toBe(true);
        const later = explainArchiveFailure({ error: 'disk_full', retry_at: '2026-11-15T14:20:00Z' }, now);
        expect(later.retryDue).toBe(false);
        expect(explainArchiveFailure({ error: 'disk_full', retry_at: null }, now).retryDue).toBe(false);
    });
});
