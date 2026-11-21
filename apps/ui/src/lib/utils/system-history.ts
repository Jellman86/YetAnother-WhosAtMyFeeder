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

/**
 * How one series is drawn, wherever it appears: its line and key on the chart, the dot on the
 * inspected sample, the swatch beside its figure, and its meter in the sidebar. The colour is a
 * fixed categorical token (`--series-*` in app.css), so it never follows the colour theme and is
 * never the accent or a status tone. The dash pattern tells two lines apart without colour.
 */
export interface SeriesStyle {
    /** The colour token, `series-1` to `series-4`. */
    colour: SeriesColour;
    /** SVG stroke class for the line and the key. */
    stroke: string;
    /** Background class for a swatch or a meter's fill. */
    fill: string;
    /** Text class whose `currentColor` paints the inspected-sample dot. */
    marker: string;
    /** Dash pattern, so two lines are told apart without relying on colour. */
    dash: string | null;
}

type SeriesColour = 'series-1' | 'series-2' | 'series-3' | 'series-4';

export interface ChartSeries extends SeriesStyle {
    id: string;
    label: string;
    scope: SeriesScope;
    load: LoadSeries;
    latest: number | null;
}

/**
 * One style per line, in a fixed order: the CPU first, then up to three accelerators. Each has its
 * own colour and its own dash, and the dash is what tells lines apart for every reader, colour-blind
 * ones included (docs/standards/design-tokens.md). A fifth line is never given a recycled colour or
 * dash; see {@link undrawnAccelerators}.
 */
export const SERIES_STYLES: readonly SeriesStyle[] = [
    { colour: 'series-1', stroke: 'stroke-series-1', fill: 'bg-series-1', marker: 'text-series-1', dash: null },
    { colour: 'series-2', stroke: 'stroke-series-2', fill: 'bg-series-2', marker: 'text-series-2', dash: '7 4' },
    { colour: 'series-3', stroke: 'stroke-series-3', fill: 'bg-series-3', marker: 'text-series-3', dash: '2 3' },
    { colour: 'series-4', stroke: 'stroke-series-4', fill: 'bg-series-4', marker: 'text-series-4', dash: '11 4 2 4' }
];

/** The CPU's style, which the sidebar's CPU meter shares with the Health chart. */
export const CPU_STYLE = SERIES_STYLES[0];

/** The style of the accelerator the server names as primary: the one the sidebar shows. */
export const PRIMARY_ACCELERATOR_STYLE = SERIES_STYLES[1];

const MAX_ACCELERATOR_LINES = SERIES_STYLES.length - 1;

type HistoryLike = Pick<SystemTelemetryHistory, 'points'> & {
    accelerators?: Accelerator[];
};

/**
 * Readable accelerators, the sidebar's own first so it takes the second colour on both surfaces.
 * The server names the sidebar's accelerator from each sample (the first measured whole-device
 * counter, else the first measured one), so a single missed reading can move it. The lead here is
 * found the same way from what does not change between polls, whether a device's counter can be
 * read at all, so one missed reading never swaps two lines' colours and dashes. Whenever every
 * device reads, it is the same device the server names.
 */
function readableAccelerators(history: HistoryLike): Accelerator[] {
    const readable = (history.accelerators ?? []).filter((accelerator) => !accelerator.unreadable);
    const lead = readable.findIndex((accelerator) => accelerator.scope === 'device');
    return lead > 0 ? [readable[lead], ...readable.slice(0, lead), ...readable.slice(lead + 1)] : readable;
}

/**
 * The lines to draw: the host's CPU, then every accelerator whose counter can be read, up to the
 * three the palette has colours for. A device that is present but unreadable is not given a line
 * it cannot fill; it is named in words instead (see {@link unreadableAccelerators}).
 */
export function chartSeries(history: HistoryLike, cpuLabel: string): ChartSeries[] {
    const latest = history.points[history.points.length - 1] ?? null;
    const series: ChartSeries[] = [
        { id: 'cpu', label: cpuLabel, scope: 'host', load: cpuLoad, latest: latest?.cpu_percent ?? null, ...CPU_STYLE }
    ];
    readableAccelerators(history)
        .slice(0, MAX_ACCELERATOR_LINES)
        .forEach((accelerator, index) => {
            series.push({
                id: accelerator.id,
                label: accelerator.label,
                scope: accelerator.scope,
                load: acceleratorLoad(accelerator.id),
                latest: latest?.accelerators?.[accelerator.id] ?? null,
                ...SERIES_STYLES[index + 1]
            });
        });
    return series;
}

/** Readable accelerators past the three the chart draws, so the panel can name them in words. */
export function undrawnAccelerators(history: HistoryLike): Accelerator[] {
    return readableAccelerators(history).slice(MAX_ACCELERATOR_LINES);
}

/**
 * The chart in words: one row per sample, at the time it was taken, oldest first, with every
 * series' reading. Nothing is borrowed from a neighbouring sample, so a short history shows only
 * what was read and a peak between two axis ticks is still there. A reading a series could not
 * take is said in words.
 */
export function sampleTable(
    points: readonly HistoryPoint[],
    series: readonly Pick<ChartSeries, 'load'>[],
    timeOf: (at: number) => string,
    notMeasured: string
): string[][] {
    return [...points]
        .sort((a, b) => a.at - b.at)
        .map((point) => [timeOf(point.at), ...series.map((line) => formatPercent(line.load(point)) ?? notMeasured)]);
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
