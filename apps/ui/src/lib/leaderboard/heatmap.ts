/** One cell of the weekday-by-hour activity grid, in the viewer's local time. */
export interface HeatmapCell {
    day_of_week: number;
    hour: number;
    count: number;
}

/**
 * One blue, light to dark for magnitude. The step nearest zero recedes toward the surface, so on
 * a dark surface the order runs the other way: a quiet hour is dim and a busy one is bright. The
 * old four-bucket scale painted the busiest hour darkest on navy, which read as the quietest.
 */
const LIGHT_RAMP = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'];
const DARK_RAMP = ['#12305a', '#184f95', '#256abf', '#3987e5', '#6da7ec', '#9ec5f4', '#cde2fb'];
const EMPTY_LIGHT = '#eef2f7';
const EMPTY_DARK = '#141d33';

function mix(from: string, to: string, t: number): string {
    const channel = (hex: string, offset: number) => parseInt(hex.slice(offset, offset + 2), 16);
    const blend = (offset: number) => Math.round(channel(from, offset) + (channel(to, offset) - channel(from, offset)) * t);
    return `#${[1, 3, 5].map((offset) => blend(offset).toString(16).padStart(2, '0')).join('')}`;
}

/** The fill for a cell: an empty hour is its own neutral, anything above zero sits on the ramp. */
export function heatmapFill(count: number, max: number, dark: boolean): string {
    if (!(count > 0) || !(max > 0)) return dark ? EMPTY_DARK : EMPTY_LIGHT;
    const ramp = dark ? DARK_RAMP : LIGHT_RAMP;
    const position = Math.min(1, count / max) * (ramp.length - 1);
    const lower = Math.floor(position);
    if (lower >= ramp.length - 1) return ramp[ramp.length - 1];
    return mix(ramp[lower], ramp[lower + 1], position - lower);
}

/** The legend's gradient, drawn from the same ramp the cells use. */
export function heatmapLegendGradient(dark: boolean): string {
    const ramp = dark ? DARK_RAMP : LIGHT_RAMP;
    return `linear-gradient(to right, ${ramp.join(', ')})`;
}

/** The hour of the day with the most activity across every weekday in the window. */
export function busiestHourOfDay(cells: readonly HeatmapCell[]): { hour: number; count: number } | null {
    const totals = new Array<number>(24).fill(0);
    for (const cell of cells) {
        if (cell.hour < 0 || cell.hour > 23) continue;
        totals[cell.hour] += Math.max(0, cell.count);
    }
    let best = -1;
    for (let hour = 0; hour < 24; hour += 1) {
        if (totals[hour] > 0 && (best === -1 || totals[hour] > totals[best])) best = hour;
    }
    return best === -1 ? null : { hour: best, count: totals[best] };
}

/** The single busiest weekday-and-hour cell, which the grid outlines. */
export function peakCell(cells: readonly HeatmapCell[]): HeatmapCell | null {
    let peak: HeatmapCell | null = null;
    for (const cell of cells) {
        if (cell.count > 0 && (!peak || cell.count > peak.count)) peak = cell;
    }
    return peak;
}
