import type { SystemTelemetryHistory } from '../api';

/**
 * Pure helpers behind the System health panel: turning the server's rolling window of
 * samples into chart geometry, and its process list into an honest breakdown of who is
 * using the host.
 */

export type HistoryPoint = SystemTelemetryHistory['points'][number];
export type ProcessLoad = SystemTelemetryHistory['processes'][number];
export type Accelerator = NonNullable<SystemTelemetryHistory['accelerators']>[number];

/** Reads one series' value out of a sample. A series is a line on the chart. */
export type LoadSeries = (point: HistoryPoint) => number | null | undefined;

export const CHART_WIDTH = 720;
export const CHART_HEIGHT = 200;

export const cpuLoad: LoadSeries = (point) => point.cpu_percent;

/** One accelerator's load, by the id the server gave it. */
export function acceleratorLoad(id: string): LoadSeries {
    return (point) => point.accelerators?.[id] ?? null;
}

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
    load: LoadSeries,
    windowSeconds: number,
    width: number = CHART_WIDTH,
    height: number = CHART_HEIGHT
): string[] {
    if (points.length === 0) return [];
    const latest = points[points.length - 1].at;
    const segments: string[] = [];
    let current: string[] = [];
    for (const point of points) {
        const value = load(point);
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
    load: LoadSeries,
    windowSeconds: number,
    width: number = CHART_WIDTH,
    height: number = CHART_HEIGHT
): string | null {
    const measured = points.filter((point) => load(point) !== null && load(point) !== undefined);
    if (measured.length < 2) return null;
    const latest = points[points.length - 1].at;
    const first = xFor(measured[0].at, latest, windowSeconds, width).toFixed(1);
    const last = xFor(measured[measured.length - 1].at, latest, windowSeconds, width).toFixed(1);
    const body = measured
        .map((point) => `${xFor(point.at, latest, windowSeconds, width).toFixed(1)},${yFor(load(point) as number, height).toFixed(1)}`)
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
export function windowSummary(points: readonly HistoryPoint[], load: LoadSeries): WindowSummary | null {
    const measured = points.filter((point) => load(point) !== null && load(point) !== undefined);
    if (measured.length === 0) return null;
    let peak = measured[0];
    let total = 0;
    for (const point of measured) {
        const value = load(point) as number;
        total += value;
        if (value > (load(peak) as number)) peak = point;
    }
    return {
        average: Math.round((total / measured.length) * 10) / 10,
        peak: load(peak) as number,
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
    /** Worker-reported accelerator runtimes behind this grouped row. */
    acceleratorLabels: string[];
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
 * Resource use at the last sample: this app's processes grouped by what they are,
 * including the accelerator runtime each worker pool actually reported. Then everything
 * else on the host is one CPU remainder, followed by idle. Rows this app has no process
 * for are left out rather than shown as zero.
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
            rssBytes: rss.length > 0 ? rss.reduce((sum, load) => sum + (load.rss_bytes as number), 0) : null,
            acceleratorLabels: Array.from(
                new Set(
                    members.map((load) => load.accelerator?.label).filter((label): label is string => Boolean(label))
                )
            )
        });
    }
    const latest = history.points[history.points.length - 1];
    if (latest) {
        rows.push({
            role: 'other_host',
            members: [],
            cpuPercent: latest.other_cpu_percent ?? null,
            rssBytes: null,
            acceleratorLabels: []
        });
        if (latest.cpu_percent !== null && latest.cpu_percent !== undefined) {
            rows.push({
                role: 'idle',
                members: [],
                cpuPercent: Math.round(Math.max(0, 100 - latest.cpu_percent) * 10) / 10,
                rssBytes: null,
                acceleratorLabels: []
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

/** What a series' number actually covers, which is not the same for every device. */
export type SeriesScope = 'host' | 'device' | 'app';

interface SeriesStyle {
    /** SVG stroke class. */
    stroke: string;
    /** Text class for the live figure. */
    text: string;
    /** Dash pattern, so two lines are told apart without relying on colour. */
    dash: string | null;
}

export interface ChartSeries extends SeriesStyle {
    id: string;
    label: string;
    scope: SeriesScope;
    load: LoadSeries;
    latest: number | null;
}

const CPU_STYLE: SeriesStyle = {
    stroke: 'stroke-blue-600 dark:stroke-blue-500',
    text: 'text-blue-700 dark:text-blue-300',
    dash: null
};

// Enough for the accelerators one host can present at once; the list repeats rather
// than running out, and the dash pattern carries the difference either way.
const ACCELERATOR_STYLES: SeriesStyle[] = [
    { stroke: 'stroke-teal-600 dark:stroke-teal-400', text: 'text-teal-700 dark:text-teal-300', dash: '7 4' },
    { stroke: 'stroke-violet-600 dark:stroke-violet-400', text: 'text-violet-700 dark:text-violet-300', dash: '2 3' },
    { stroke: 'stroke-amber-700 dark:stroke-amber-500', text: 'text-amber-800 dark:text-amber-400', dash: '11 4 2 4' }
];

type HistoryLike = Pick<SystemTelemetryHistory, 'points'> & { accelerators?: Accelerator[] };

/**
 * The lines to draw: the host's CPU, then every accelerator whose counter can be read.
 * A device that is present but unreadable is not given a line it cannot fill; it is
 * named in words instead (see {@link unreadableAccelerators}).
 */
export function chartSeries(history: HistoryLike, cpuLabel: string): ChartSeries[] {
    const latest = history.points[history.points.length - 1] ?? null;
    const series: ChartSeries[] = [
        { id: 'cpu', label: cpuLabel, scope: 'host', load: cpuLoad, latest: latest?.cpu_percent ?? null, ...CPU_STYLE }
    ];
    const readable = (history.accelerators ?? []).filter((accelerator) => !accelerator.unreadable);
    readable.forEach((accelerator, index) => {
        series.push({
            id: accelerator.id,
            label: accelerator.label,
            scope: accelerator.scope,
            load: acceleratorLoad(accelerator.id),
            latest: latest?.accelerators?.[accelerator.id] ?? null,
            ...ACCELERATOR_STYLES[index % ACCELERATOR_STYLES.length]
        });
    });
    return series;
}

/** Accelerators this host has but cannot measure, so the panel can say so by name. */
export function unreadableAccelerators(history: HistoryLike): Accelerator[] {
    return (history.accelerators ?? []).filter((accelerator) => Boolean(accelerator.unreadable));
}

/**
 * Where one series sits at the inspected sample, for the dot that ties the crosshair
 * to the line. A sample the series could not measure has no dot.
 */
export function markerFor(
    points: readonly HistoryPoint[],
    index: number,
    load: LoadSeries,
    windowSeconds: number,
    width: number = CHART_WIDTH,
    height: number = CHART_HEIGHT
): { x: number; y: number } | null {
    const point = points[index];
    if (!point) return null;
    const value = load(point);
    if (value === null || value === undefined) return null;
    return {
        x: xFor(point.at, points[points.length - 1].at, windowSeconds, width),
        y: yFor(value, height)
    };
}
