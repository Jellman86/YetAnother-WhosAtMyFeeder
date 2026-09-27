import { describe, expect, it } from 'vitest';
import { busiestHourOfDay, dayTotals, heatmapFill, hourlyTotals, moveGridPosition, peakCell } from './heatmap';

function lightness(hex: string): number {
    const [r, g, b] = [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

describe('heatmapFill', () => {
    it('gives an empty hour the neutral, not the lightest step of the ramp', () => {
        expect(heatmapFill(0, 33, false)).toBe('#eef2f7');
        expect(heatmapFill(0, 33, true)).toBe('#141d33');
        expect(heatmapFill(1, 33, false)).not.toBe('#eef2f7');
    });

    it('darkens with activity on a light surface', () => {
        const fills = [1, 8, 16, 25, 33].map((count) => lightness(heatmapFill(count, 33, false)));
        expect([...fills].sort((a, b) => b - a)).toEqual(fills);
    });

    it('brightens with activity on a dark surface, so the busiest hour stands out', () => {
        const fills = [1, 8, 16, 25, 33].map((count) => lightness(heatmapFill(count, 33, true)));
        expect([...fills].sort((a, b) => a - b)).toEqual(fills);
    });

    it('clamps a count above the maximum to the last step', () => {
        expect(heatmapFill(50, 33, true)).toBe(heatmapFill(33, 33, true));
    });
});

describe('busiestHourOfDay', () => {
    it('adds every weekday together before choosing an hour', () => {
        const cells = [
            { day_of_week: 1, hour: 7, count: 10 },
            { day_of_week: 2, hour: 9, count: 6 },
            { day_of_week: 3, hour: 9, count: 6 },
        ];
        expect(busiestHourOfDay(cells)).toEqual({ hour: 9, count: 12 });
    });

    it('returns null for a window with no activity', () => {
        expect(busiestHourOfDay([{ day_of_week: 1, hour: 7, count: 0 }])).toBeNull();
    });
});

describe('peakCell', () => {
    it('picks the single busiest weekday and hour', () => {
        const cells = [
            { day_of_week: 1, hour: 7, count: 10 },
            { day_of_week: 4, hour: 12, count: 33 },
        ];
        expect(peakCell(cells)).toEqual({ day_of_week: 4, hour: 12, count: 33 });
        expect(peakCell([])).toBeNull();
    });
});

describe('the heatmap margins', () => {
    const cells = [
        { day_of_week: 1, hour: 7, count: 4 },
        { day_of_week: 2, hour: 7, count: 6 },
        { day_of_week: 2, hour: 9, count: 1 },
    ];

    it('adds each hour across the week', () => {
        const totals = hourlyTotals(cells);
        expect(totals).toHaveLength(24);
        expect(totals[7]).toBe(10);
        expect(totals[9]).toBe(1);
        expect(totals[0]).toBe(0);
    });

    it('adds each weekday across the day', () => {
        expect(dayTotals(cells)).toEqual([0, 4, 7, 0, 0, 0, 0]);
    });
});

describe('moving through the grid with the keyboard', () => {
    it('steps by hour and by row and stops at the edges', () => {
        expect(moveGridPosition({ row: 0, hour: 0 }, 'ArrowLeft', 7)).toEqual({ row: 0, hour: 0 });
        expect(moveGridPosition({ row: 0, hour: 0 }, 'ArrowRight', 7)).toEqual({ row: 0, hour: 1 });
        expect(moveGridPosition({ row: 6, hour: 5 }, 'ArrowDown', 7)).toEqual({ row: 6, hour: 5 });
        expect(moveGridPosition({ row: 3, hour: 5 }, 'ArrowUp', 7)).toEqual({ row: 2, hour: 5 });
        expect(moveGridPosition({ row: 3, hour: 5 }, 'End', 7)).toEqual({ row: 3, hour: 23 });
        expect(moveGridPosition({ row: 3, hour: 5 }, 'Home', 7)).toEqual({ row: 3, hour: 0 });
    });

    it('ignores keys that are not movement', () => {
        expect(moveGridPosition({ row: 3, hour: 5 }, 'Enter', 7)).toBeNull();
    });
});
