import type { SystemTelemetryHistory } from '../api';

/**
 * Pure helpers behind the System health panel: turning the server's rolling window of
 * samples into chart geometry, and its process list into an honest breakdown of who is
 * using the host.
 */

export type HistoryPoint = SystemTelemetryHistory['points'][number];
export type ProcessLoad = SystemTelemetryHistory['processes'][number];
export type LoadSeries = 'cpu_percent' | 'accelerator_percent';

export const CHART_WIDTH = 720;
export const CHART_HEIGHT = 200;

/** Where a sample falls across the window: the right edge is the newest sample. */
function xFor(at: number, latest: number, windowSeconds: number, width: number): number {
    const start = latest - windowSeconds;
    return ((at - start) / windowSeconds) * width;
}

function yFor(percent: number, height: number): number {
    return height - (Math.max(0, Math.min(100, percent)) / 100) * height;
}

/**
 * SVG polyline points for one series. A sample the host could not measure breaks the
 * line rather than being drawn as zero, so a gap reads as a gap.
 */
export function seriesSegments(
    points: readonly HistoryPoint[],
    series: LoadSeries,
    windowSeconds: number,
    width: number = CHART_WIDTH,
    height: number = CHART_HEIGHT
): string[] {
    if (points.length === 0) return [];
    const latest = points[points.length - 1].at;
    const segments: string[] = [];
    let current: string[] = [];
    for (const point of points) {
        const value = point[series];
        if (value === null || value === undefined) {
            if (current.length > 0) segments.push(current.join(' '));
            current = [];
            continue;
        }
        current.push(`${xFor(point.at, latest, windowSeconds, width).toFixed(1)},${yFor(value, height).toFixed(1)}`);
    }
    if (current.length > 0) segments.push(current.join(' '));
    return segments;
}

/** The filled area under the CPU line, closed along the baseline. */
export function seriesArea(
    points: readonly HistoryPoint[],
    series: LoadSeries,
    windowSeconds: number,
    width: number = CHART_WIDTH,
    height: number = CHART_HEIGHT
): string | null {
    const measured = points.filter((point) => point[series] !== null && point[series] !== undefined);
    if (measured.length < 2) return null;
    const latest = points[points.length - 1].at;
    const first = xFor(measured[0].at, latest, windowSeconds, width).toFixed(1);
    const last = xFor(measured[measured.length - 1].at, latest, windowSeconds, width).toFixed(1);
    const body = measured
        .map((point) => `${xFor(point.at, latest, windowSeconds, width).toFixed(1)},${yFor(point[series] as number, height).toFixed(1)}`)
        .join(' ');
    return `${first},${height} ${body} ${last},${height}`;
}

/** Evenly spaced time ticks across the window, as epoch seconds with their x position. */
export function timeTicks(
    points: readonly HistoryPoint[],
    windowSeconds: number,
    count: number = 4,
    width: number = CHART_WIDTH
): { at: number; x: number }[] {
    if (points.length === 0) return [];
    const latest = points[points.length - 1].at;
    const start = latest - windowSeconds;
    return Array.from({ length: count }, (_, index) => {
        const at = start + (windowSeconds * index) / (count - 1);
        return { at, x: (index / (count - 1)) * width };
    });
}

/** The sample nearest a horizontal position, for the hover crosshair. */
export function pointAt(
    points: readonly HistoryPoint[],
    x: number,
    windowSeconds: number,
    width: number = CHART_WIDTH
): { point: HistoryPoint; index: number; x: number } | null {
    if (points.length === 0) return null;
    const latest = points[points.length - 1].at;
    let best = 0;
    let bestDistance = Number.POSITIVE_INFINITY;
    points.forEach((point, index) => {
        const distance = Math.abs(xFor(point.at, latest, windowSeconds, width) - x);
        if (distance < bestDistance) {
            bestDistance = distance;
            best = index;
        }
    });
    return { point: points[best], index: best, x: xFor(points[best].at, latest, windowSeconds, width) };
}

export interface WindowSummary {
    average: number;
    peak: number;
    peakAt: number;
}

/** What the window held, in words a screen reader or a hurried owner can take in. */
export function windowSummary(points: readonly HistoryPoint[], series: LoadSeries): WindowSummary | null {
    const measured = points.filter((point) => point[series] !== null && point[series] !== undefined);
    if (measured.length === 0) return null;
    let peak = measured[0];
    let total = 0;
    for (const point of measured) {
        const value = point[series] as number;
        total += value;
        if (value > (peak[series] as number)) peak = point;
    }
    return {
        average: Math.round((total / measured.length) * 10) / 10,
        peak: peak[series] as number,
        peakAt: peak.at
    };
}

export type ShareRole = ProcessLoad['role'] | 'other_host' | 'idle';

export interface ShareRow {
    role: ShareRole;
    /** Worker names or process names behind the row, newest first as the server listed them. */
    members: string[];
    cpuPercent: number | null;
    rssBytes: number | null;
}

const NAMED_ROLES: ProcessLoad['role'][] = [
    'main',
    'live_worker',
    'background_worker',
    'video_worker',
    'ffmpeg',
    'other_child'
];

/**
 * Who is using the CPU at the last sample: this app's processes grouped by what they are,
 * then everything else on the host as one remainder, then idle. Rows this app has no
 * process for are left out rather than shown as zero.
 */
export function shareRows(history: Pick<SystemTelemetryHistory, 'points' | 'processes'>): ShareRow[] {
    const rows: ShareRow[] = [];
    for (const role of NAMED_ROLES) {
        const members = history.processes.filter((load) => load.role === role);
        if (members.length === 0) continue;
        const measured = members.filter((load) => load.cpu_percent !== null && load.cpu_percent !== undefined);
        const rss = members.filter((load) => load.rss_bytes !== null && load.rss_bytes !== undefined);
        rows.push({
            role,
            members: members.map((load) => load.label),
            cpuPercent:
                measured.length > 0
                    ? Math.round(measured.reduce((sum, load) => sum + (load.cpu_percent as number), 0) * 10) / 10
                    : null,
            rssBytes: rss.length > 0 ? rss.reduce((sum, load) => sum + (load.rss_bytes as number), 0) : null
        });
    }
    const latest = history.points[history.points.length - 1];
    if (latest) {
        rows.push({ role: 'other_host', members: [], cpuPercent: latest.other_cpu_percent ?? null, rssBytes: null });
        if (latest.cpu_percent !== null && latest.cpu_percent !== undefined) {
            rows.push({
                role: 'idle',
                members: [],
                cpuPercent: Math.round(Math.max(0, 100 - latest.cpu_percent) * 10) / 10,
                rssBytes: null
            });
        }
    }
    return rows;
}

export function formatBytes(bytes: number | null | undefined): string | null {
    if (bytes === null || bytes === undefined) return null;
    if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
    if (bytes >= 1024 ** 2) return `${Math.round(bytes / 1024 ** 2)} MB`;
    return `${Math.round(bytes / 1024)} KB`;
}

export function formatPercent(value: number | null | undefined): string | null {
    if (value === null || value === undefined) return null;
    return `${value.toFixed(1)}%`;
}
