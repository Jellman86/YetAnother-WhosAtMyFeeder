import { describe, expect, it } from 'vitest';
import { bucketPrecipitation, chartTable, shareTable } from './chart-table';

const format = (value: number): string => value.toLocaleString('en-GB');

describe('chartTable', () => {
    it('lists every drawn value under its label, one column per visible series', () => {
        const table = chartTable('Date', ['1 Nov', '2 Nov'], [
            { label: 'Great Tit', data: [3, 1] },
            { label: 'Robin', data: [0, 2] }
        ], format);
        expect(table).toEqual({ columns: ['Date', 'Great Tit', 'Robin'], rows: [['1 Nov', '3', '0'], ['2 Nov', '1', '2']] });
    });

    it('leaves out a series the reader hid, as the chart does', () => {
        const table = chartTable('Date', ['1 Nov'], [{ label: 'Great Tit', data: [3] }, { label: 'Robin', data: [2], hidden: true }], format);
        expect(table.columns).toEqual(['Date', 'Great Tit']);
        expect(table.rows).toEqual([['1 Nov', '3']]);
    });

    it('says a missing value with a dash, not a zero', () => {
        const table = chartTable('Date', ['1 Nov', '2 Nov'], [{ label: 'Temperature', data: [Number.NaN, 4.5] }], format);
        expect(table.rows).toEqual([['1 Nov', '—'], ['2 Nov', '4.5']]);
    });

    it('joins further series drawn on their own small charts for the same labels', () => {
        const table = chartTable('Date', ['1 Nov'], [{ label: 'Visits', data: [3] }, { label: 'Temperature (°C)', data: [8] }], format);
        expect(table.columns).toEqual(['Date', 'Visits', 'Temperature (°C)']);
    });

    it('writes a series with a unit in its own format', () => {
        const table = chartTable('Date', ['1 Nov'], [{ label: 'Visits', data: [3] }, { label: 'Temperature', data: [8.25], format: (value) => `${value.toFixed(1)}°C` }], format);
        expect(table.rows).toEqual([['1 Nov', '3', '8.3°C']]);
    });
});

describe('shareTable', () => {
    const columns: [string, string, string] = ['Species', 'Visits', 'Share'];

    it('gives each slice its share of what the ring shows', () => {
        expect(shareTable(columns, ['Great Tit', 'Robin'], [60, 40], [], format).rows).toEqual([['Great Tit', '60', '60%'], ['Robin', '40', '40%']]);
    });

    it('measures a share against the slices still shown once one is hidden, as the ring does', () => {
        expect(shareTable(columns, ['Great Tit', 'Robin'], [60, 40], [1], format).rows).toEqual([['Great Tit', '60', '100%']]);
    });

    it('says a dash for a share of nothing', () => {
        expect(shareTable(columns, ['Great Tit'], [0], [], format).rows).toEqual([['Great Tit', '0', '—']]);
    });
});

describe('bucketPrecipitation', () => {
    it('is the larger of rain and snow together or the reported total', () => {
        expect(bucketPrecipitation(1.2, 0.3, 1)).toBe(1.5);
        expect(bucketPrecipitation(0.2, 0, 0.9)).toBe(0.9);
    });

    it('counts a missing reading as none, and never goes below zero', () => {
        expect(bucketPrecipitation(null, null, null)).toBe(0);
        expect(bucketPrecipitation(-1, null, 0.4)).toBe(0.4);
    });
});
