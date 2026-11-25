import { describe, expect, it } from 'vitest';
import { LEADERBOARD_SPANS, shortenedWindowStart, trendGap, type WindowReading } from './period';

const whole: WindowReading = { start: '2034-03-10T23:00:00+00:00', shortened: false, complete: true, comparable: true };
const cut: WindowReading = { start: '2034-03-11T00:00:00+00:00', shortened: true, complete: false, comparable: false };

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

    it('says the windows differ when they could not be compared, whatever the history', () => {
        expect(trendGap('seen', cut, whole)).toBe('not_comparable');
        expect(trendGap('both', whole, cut)).toBe('not_comparable');
        expect(trendGap('heard', cut, whole)).toBeNull();
    });

    it('treats a source that did not load as unmeasured, not as a reason', () => {
        expect(trendGap('heard', whole, null)).toBe('history');
    });
});
