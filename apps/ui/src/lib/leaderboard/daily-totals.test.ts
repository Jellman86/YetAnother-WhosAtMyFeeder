import { describe, expect, it } from 'vitest';
import { dailyTotalsNote } from './daily-totals';

describe('dailyTotalsNote', () => {
    it('says nothing when a chart counted only stored captures', () => {
        expect(dailyTotalsNote(null)).toBeNull();
        expect(dailyTotalsNote({ totals_through: null, complete_from: null, partial: false })).toBeNull();
    });

    it('names the first day counted from stored captures', () => {
        expect(dailyTotalsNote({ totals_through: '2036-02-10', complete_from: null, partial: false })).toEqual({
            firstStoredDay: '2036-02-11',
            partialBefore: null
        });
    });

    it('crosses month and year ends', () => {
        expect(dailyTotalsNote({ totals_through: '2036-12-31', partial: false })?.firstStoredDay).toBe('2037-01-01');
        expect(dailyTotalsNote({ totals_through: '2036-02-29', partial: false })?.firstStoredDay).toBe('2036-03-01');
    });

    it('says from when the totals are whole when some were counted after captures were already gone', () => {
        expect(dailyTotalsNote({ totals_through: '2036-02-10', complete_from: '2036-02-04', partial: true })).toEqual({
            firstStoredDay: '2036-02-11',
            partialBefore: '2036-02-04'
        });
        // No whole total yet: every total shown may be low.
        expect(dailyTotalsNote({ totals_through: '2036-02-10', complete_from: null, partial: true })).toEqual({
            firstStoredDay: '2036-02-11',
            partialBefore: '2036-02-11'
        });
    });
});
