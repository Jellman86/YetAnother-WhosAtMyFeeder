import type { Action } from 'svelte/action';
import type { ApexOptions } from 'apexcharts';

type ApexModule = typeof import('apexcharts');

function normalizeSeriesPoint(point: any): any {
    if (point === null || point === undefined) return null;
    if (typeof point === 'number') {
        return Number.isFinite(point) ? point : null;
    }
    if (typeof point !== 'object') return null;
    const x = (point as any).x;
    const y = (point as any).y;
    if (x !== undefined && x !== null && !Number.isFinite(Number(x))) {
        return null;
    }
    if (y !== undefined && y !== null && !Number.isFinite(Number(y))) {
        return { ...(point as Record<string, any>), y: null };
    }
    return point;
}

function normalizeOptions(options: ApexOptions): ApexOptions {
    const next: any = { ...(options as any) };
    const series = Array.isArray((options as any)?.series)
        ? (options as any).series
            .filter(Boolean)
            .map((entry: any) => ({
                ...entry,
                data: Array.isArray(entry?.data)
                    ? entry.data
                        .map((point: any) => normalizeSeriesPoint(point))
                        .filter((point: any) => point !== null)
                    : []
            }))
        : [];

    next.series = series;

    if (Array.isArray(next.yaxis)) {
        const seriesNames = new Set(series.map((entry: any) => entry?.name).filter(Boolean));
        const normalizedYAxes = next.yaxis
            .filter((axis: any) => !axis?.seriesName || seriesNames.has(axis.seriesName))
            .map((axis: any) => ({ ...axis }));
        if (normalizedYAxes.length > 0) {
            next.yaxis = normalizedYAxes;
        } else {
            next.yaxis = undefined;
        }
    }

    if (next.annotations && Array.isArray(next.annotations.xaxis)) {
        next.annotations = {
            ...next.annotations,
            xaxis: next.annotations.xaxis.filter((ann: any) => {
                const x = Number(ann?.x);
                if (!Number.isFinite(x)) return false;
                if (ann?.x2 !== undefined && ann?.x2 !== null && !Number.isFinite(Number(ann.x2))) return false;
                return true;
            })
        };
    }

    if (next.stroke) {
        next.stroke = { ...next.stroke };
        if (Array.isArray(next.stroke.width) && next.stroke.width.length !== series.length) {
            next.stroke.width = series.map((entry: any) => (entry?.type === 'bar' ? 0 : 2));
        }
        if (Array.isArray(next.stroke.dashArray) && next.stroke.dashArray.length !== series.length) {
            next.stroke.dashArray = series.map(() => 0);
        }
    }

    if (next.fill) {
        next.fill = { ...next.fill };
        if (Array.isArray(next.fill.type) && next.fill.type.length !== series.length) {
            next.fill.type = series.map((entry: any) => (entry?.type === 'area' ? 'gradient' : 'solid'));
        }
    }

    if (!series.length) {
        next.series = [{ name: 'Series', type: 'line', data: [] }];
    }

    return next as ApexOptions;
}

export const chart: Action<HTMLElement, ApexOptions> = (node, options) => {
    let chartInstance: any = null;
    let ApexChartsCtor: any = null;
    let pendingOptions = normalizeOptions(options);
    let destroyed = false;
    let initPromise: Promise<void> | null = null;

    async function init() {
        if (initPromise) return initPromise;
        initPromise = (async () => {
            const mod = await import('apexcharts');
            if (destroyed) return;
            const ApexCharts = (mod as any).default ?? mod;
            ApexChartsCtor = ApexCharts;
            chartInstance = new ApexCharts(node, pendingOptions);
            await chartInstance.render();
            (node as any).__apexchart = chartInstance;
        })();
        return initPromise;
    }

    void init().catch((error: unknown) => {
        // Prevent unhandled promise rejections when Apex fails initial render.
        console.error('Apex initial render failed', error);
    });

    return {
        update(newOptions) {
            pendingOptions = normalizeOptions(newOptions);
            if (chartInstance) {
                void Promise
                    .resolve(chartInstance.updateOptions(pendingOptions, true, true))
                    .catch(async (error: unknown) => {
                        console.error('Apex updateOptions failed, recreating chart instance', error);
                        if (destroyed || !ApexChartsCtor) return;
                        try {
                            await chartInstance.destroy();
                        } catch {
                            // best effort cleanup
                        }
                        try {
                            chartInstance = new ApexChartsCtor(node, pendingOptions);
                            await chartInstance.render();
                            (node as any).__apexchart = chartInstance;
                        } catch (recreateError) {
                            chartInstance = null;
                            (node as any).__apexchart = null;
                            console.error('Apex chart recreation failed', recreateError);
                        }
                    })
                    .catch((chainError: unknown) => {
                        // Defensive final catch for any unexpected async chain rejection.
                        console.error('Apex update chain failed', chainError);
                    });
            }
        },
        destroy() {
            destroyed = true;
            if (chartInstance) {
                chartInstance.destroy();
                chartInstance = null;
            }
            (node as any).__apexchart = null;
        }
    };
};
