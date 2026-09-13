import { describe, expect, it } from 'vitest';
import {
    formatBytes,
    formatPercent,
    pointAt,
    seriesArea,
    seriesSegments,
    shareRows,
    timeTicks,
    windowSummary,
    type HistoryPoint,
    type ProcessLoad
} from './system-history';

function point(at: number, cpu: number | null, npu: number | null = null, app: number | null = null): HistoryPoint {
    return {
        at,
        cpu_percent: cpu,
        accelerator_percent: npu,
        app_cpu_percent: app,
        other_cpu_percent: cpu !== null && app !== null ? Math.max(0, cpu - app) : null
    };
}

function load(role: ProcessLoad['role'], label: string, cpu: number | null, rss: number | null): ProcessLoad {
    return { pid: 1, role, label, detail: null, cpu_percent: cpu, rss_bytes: rss };
}

describe('system history chart geometry', () => {
    it('places the newest sample at the right edge and scales percent to the height', () => {
        const points = [point(100, 0), point(200, 50), point(300, 100)];
        const [segment] = seriesSegments(points, 'cpu_percent', 200, 200, 100);
        expect(segment).toBe('0.0,100.0 100.0,50.0 200.0,0.0');
    });

    it('breaks the line where the host could not be measured, rather than drawing zero', () => {
        const points = [point(0, 10), point(5, null), point(10, 30), point(15, 40)];
        const segments = seriesSegments(points, 'cpu_percent', 15, 150, 100);
        expect(segments).toHaveLength(2);
        expect(segments[0]).toBe('0.0,90.0');
        expect(segments[1]).toBe('100.0,70.0 150.0,60.0');
    });

    it('closes the area along the baseline and needs two measured samples', () => {
        expect(seriesArea([point(0, 10)], 'cpu_percent', 10, 100, 100)).toBeNull();
        expect(seriesArea([point(0, 10), point(10, 20)], 'cpu_percent', 10, 100, 100)).toBe(
            '0.0,100 0.0,90.0 100.0,80.0 100.0,100'
        );
    });

    it('spaces time ticks across the window and finds the nearest sample to a position', () => {
        const points = [point(1000, 1), point(1300, 2), point(1600, 3)];
        const ticks = timeTicks(points, 600, 3, 600);
        expect(ticks).toEqual([
            { at: 1000, x: 0 },
            { at: 1300, x: 300 },
            { at: 1600, x: 600 }
        ]);
        expect(pointAt(points, 320, 600, 600)?.index).toBe(1);
        expect(pointAt([], 10, 600)).toBeNull();
    });

    it('summarises the window as an average and a dated peak', () => {
        const points = [point(10, 10), point(20, 70), point(30, null), point(40, 40)];
        expect(windowSummary(points, 'cpu_percent')).toEqual({ average: 40, peak: 70, peakAt: 20 });
        expect(windowSummary(points, 'accelerator_percent')).toBeNull();
    });
});

describe('who is using the host', () => {
    it("groups this app's processes by what they are, then the rest of the host, then idle", () => {
        const rows = shareRows({
            points: [point(1, 40, 0, 30.5)],
            processes: [
                load('main', 'YA-WAMF', 3, 1000),
                load('video_worker', 'video-0', 25.5, 400),
                load('live_worker', 'live-0', 2, 300),
                load('live_worker', 'live-1', null, 300)
            ]
        });
        expect(rows.map((row) => row.role)).toEqual(['main', 'live_worker', 'video_worker', 'other_host', 'idle']);
        const live = rows.find((row) => row.role === 'live_worker');
        expect(live).toEqual({ role: 'live_worker', members: ['live-0', 'live-1'], cpuPercent: 2, rssBytes: 600 });
        expect(rows.find((row) => row.role === 'other_host')?.cpuPercent).toBe(9.5);
        expect(rows.find((row) => row.role === 'idle')?.cpuPercent).toBe(60);
    });

    it('leaves out roles this app has no process for and never invents a remainder', () => {
        expect(shareRows({ points: [], processes: [load('main', 'YA-WAMF', 1, 1)] }).map((row) => row.role)).toEqual([
            'main'
        ]);
    });

    it('formats bytes and percentages, and says nothing for an unmeasured value', () => {
        expect(formatBytes(1_358_540_800)).toBe('1.27 GB');
        expect(formatBytes(62 * 1024 * 1024)).toBe('62 MB');
        expect(formatBytes(null)).toBeNull();
        expect(formatPercent(16.3)).toBe('16.3%');
        expect(formatPercent(undefined)).toBeNull();
    });
});
