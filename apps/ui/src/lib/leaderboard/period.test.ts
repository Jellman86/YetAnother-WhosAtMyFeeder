import { describe, expect, it } from 'vitest';
import { LEADERBOARD_SPANS, shortenedWindowStart, trendGap, windowsAgree, type WindowReading } from './period';

const whole: WindowReading = { start: '2034-03-10T23:00:00+00:00', shortened: false, complete: true, mismatch: null };
const cut: WindowReading = { start: '2034-03-11T00:00:00+00:00', shortened: true, complete: false, mismatch: 'shared_window' };

describe('the leaderboard periods', () => {
    it('runs from Today to All time, keeping day for the last 24 hours', () => {
        expect(LEADERBOARD_SPANS).toEqual(['today', 'day', 'week', 'month', 'all']);
    });
});

describe('shortenedWindowStart', () => {
    it('names no start when the window is the one the span asks for', () => {
        expect(shortenedWindowStart('seen', whole, whole)).toBeNull();
        expect(shortenedWindowStart('both', whole, null)).toBeNull();
    });

    it('names the start of the source the ranking counts', () => {
        expect(shortenedWindowStart('seen', cut, whole)).toBe(cut.start);
        expect(shortenedWindowStart('heard', whole, cut)).toBe(cut.start);
        expect(shortenedWindowStart('heard', cut, whole)).toBeNull();
        expect(shortenedWindowStart('seen', whole, cut)).toBeNull();
    });

    it('names a shortened start for Both when either source was cut', () => {
        expect(shortenedWindowStart('both', whole, cut)).toBe(cut.start);
        expect(shortenedWindowStart('both', cut, whole)).toBe(cut.start);
    });
});

describe('trendGap', () => {
    it('has no gap when the trend was measured', () => {
        expect(trendGap('seen', whole, whole)).toBeNull();
        expect(trendGap('both', whole, whole)).toBeNull();
    });

    it('blames the history only when the windows were like for like', () => {
        const young = { ...whole, complete: false };
        expect(trendGap('seen', young, whole)).toBe('history');
        expect(trendGap('heard', whole, young)).toBe('history');
    });

    it('gives the reason the server measured, whatever the history', () => {
        expect(trendGap('seen', cut, whole)).toBe('shared_window');
        expect(trendGap('both', whole, cut)).toBe('shared_window');
        expect(trendGap('heard', cut, whole)).toBeNull();
    });

    it('tells a guest on a clock-change day about the clocks, not the shared window', () => {
        const clocks = { ...whole, complete: false, mismatch: 'clock_change' as const };
        expect(trendGap('seen', clocks, whole)).toBe('clock_change');
        expect(trendGap('both', whole, clocks)).toBe('clock_change');
    });

    it('names cleanup when it removed captures from a compared window', () => {
        expect(trendGap('seen', { ...whole, complete: false, mismatch: 'cleanup' }, whole)).toBe('cleanup');
    });

    it('treats a source that did not load as unmeasured, not as a reason', () => {
        expect(trendGap('heard', whole, null)).toBe('history');
    });
});

describe('windowsAgree', () => {
    it('accepts one start written either way, and answers that named none', () => {
        expect(windowsAgree(['2034-03-10T23:00:00+00:00', '2034-03-10T23:00:00Z', null, undefined])).toBe(true);
        expect(windowsAgree([])).toBe(true);
    });

    it('refuses answers from either side of midnight', () => {
        expect(windowsAgree(['2034-03-10T23:00:00Z', '2034-03-11T23:00:00Z'])).toBe(false);
    });
});
