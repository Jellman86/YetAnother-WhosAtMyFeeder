import { describe, expect, it } from 'vitest';
import { INITIAL_READ, readFreshness, settleRead } from './read-freshness';

describe('read freshness', () => {
    it('keeps a reading marked stale while a retry is in flight, and fresh only once a read succeeds', () => {
        let read = settleRead(INITIAL_READ, 1, { ok: true, at: 1_000 });
        read = settleRead(read, 2, { ok: false, error: 'HTTP 500' });
        expect(readFreshness(true, read)).toBe('stale');
        // Starting read 3 changes nothing: retained data is not current until read 3 succeeds.
        expect(readFreshness(true, read)).toBe('stale');
        read = settleRead(read, 3, { ok: true, at: 3_000 });
        expect(readFreshness(true, read)).toBe('read');
        expect(read.readAt).toBe(3_000);
    });

    it('drops an earlier failure once a later read, such as clear-and-refresh, succeeds', () => {
        let read = settleRead(INITIAL_READ, 1, { ok: false, error: 'HTTP 500' });
        expect(readFreshness(false, read)).toBe('failed');
        read = settleRead(read, 2, { ok: true, at: 2_000 });
        expect(readFreshness(true, read)).toBe('read');
        expect(read.error).toBeNull();
    });

    it('ignores a response that settles after a newer read already did', () => {
        let read = settleRead(INITIAL_READ, 2, { ok: true, at: 2_000 });
        read = settleRead(read, 1, { ok: false, error: 'late failure' });
        expect(readFreshness(true, read)).toBe('read');
        read = settleRead(read, 1, { ok: true, at: 1_000 });
        expect(read.readAt).toBe(2_000);
    });

    it('is reading before anything has settled, and failed only when the first read failed', () => {
        expect(readFreshness(false, INITIAL_READ)).toBe('reading');
        expect(readFreshness(false, settleRead(INITIAL_READ, 1, { ok: false, error: 'x' }))).toBe('failed');
    });
});
