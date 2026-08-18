export type SourceMode = 'seen' | 'heard' | 'both';

export interface SourceMetricRow {
    count: number;
    heard_count: number;
    delta?: number | null;
    percent?: number | null;
    prev_count?: number | null;
    heard_delta?: number | null;
    heard_percent?: number | null;
    heard_prev_count?: number | null;
    last_seen?: string | null;
    heard_last?: string | null;
}

export function countForMode(row: SourceMetricRow, mode: SourceMode): number {
    if (mode === 'heard') return row.heard_count;
    if (mode === 'both') return row.count + row.heard_count;
    return row.count;
}

export function deltaForMode(row: SourceMetricRow, mode: SourceMode): number | null {
    if (mode === 'heard') return row.heard_delta ?? null;
    if (mode === 'both') return (row.delta ?? 0) + (row.heard_delta ?? 0);
    return row.delta ?? null;
}

// A ratio against a handful of prior visits reads as noise ("+92 (9200.0%)" from a
// baseline of one), so the percentage only appears when the previous window is big
// enough to compare against and the ratio stays inside a readable range.
const MIN_TREND_BASELINE = 5;
const MAX_TREND_PERCENT = 1000;

function formatTrend(
    delta: number | null,
    percent: number | null,
    previousCount: number | null
): string {
    if (!delta) return '0';
    const count = `${delta > 0 ? '+' : ''}${delta}`;
    if (!previousCount || percent === null) return count;
    if (previousCount < MIN_TREND_BASELINE || Math.abs(percent) >= MAX_TREND_PERCENT) return count;
    return `${count} (${percent.toFixed(1)}%)`;
}

export function trendForMode(row: SourceMetricRow, mode: SourceMode): string {
    const delta = deltaForMode(row, mode);
    if (mode === 'seen') {
        return formatTrend(delta, row.percent ?? null, row.prev_count ?? null);
    }
    if (mode === 'heard') {
        return formatTrend(delta, row.heard_percent ?? null, row.heard_prev_count ?? null);
    }

    const previousCount = (row.prev_count ?? 0) + (row.heard_prev_count ?? 0);
    const percent = previousCount > 0 && delta !== null ? (delta / previousCount) * 100 : null;
    return formatTrend(delta, percent, previousCount);
}

export function activityTimestampForMode(
    row: SourceMetricRow,
    mode: SourceMode
): string | null {
    if (mode === 'seen') return row.last_seen ?? null;
    if (mode === 'heard') return row.heard_last ?? null;

    const seenAt = row.last_seen ? Date.parse(row.last_seen) : Number.NaN;
    const heardAt = row.heard_last ? Date.parse(row.heard_last) : Number.NaN;
    if (Number.isNaN(seenAt)) return row.heard_last ?? row.last_seen ?? null;
    if (Number.isNaN(heardAt)) return row.last_seen ?? row.heard_last ?? null;
    return heardAt > seenAt ? (row.heard_last ?? null) : (row.last_seen ?? null);
}
