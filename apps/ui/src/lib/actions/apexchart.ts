import type { Action } from 'svelte/action';
import type ApexCharts from 'apexcharts';
import type { ApexOptions } from 'apexcharts';

type ApexConstructor = typeof ApexCharts;
type ApexInstance = InstanceType<ApexConstructor>;
type ChartNode = HTMLElement & { __apexchart?: ApexInstance | null };

function asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

function resolveApexConstructor(moduleValue: unknown): ApexConstructor {
    const candidate = asRecord(moduleValue).default ?? moduleValue;
    if (typeof candidate !== 'function') {
        throw new TypeError('ApexCharts module did not export a constructor');
    }
    return candidate as ApexConstructor;
}

function normalizeSeriesPoint(point: unknown): unknown {
    if (point === null || point === undefined) return null;
    if (typeof point === 'number') {
        return Number.isFinite(point) ? point : null;
    }
    if (typeof point !== 'object') return null;
    const record = asRecord(point);
    const x = record.x;
    const y = record.y;
    if (x !== undefined && x !== null) {
        if (typeof x === 'number') {
            if (!Number.isFinite(x)) return null;
        } else if (typeof x === 'string') {
            // Allow categorical axes (e.g. heatmaps with "00:00" labels).
            if (!x.length) return null;
        } else {
            // Keep Date/typed values that Apex can consume, drop unsupported primitives.
            if (typeof x !== 'object') return null;
        }
    }
    if (y !== undefined && y !== null && !Number.isFinite(Number(y))) {
        return { ...record, y: null };
    }
    return point;
}

function normalizeOptions(options: ApexOptions): ApexOptions {
    const next = { ...asRecord(options) };
    const rawSeries = next.series;

    // Donut/pie charts use a flat number array as series rather than the
    // [{name, type, data[]}] format used by line/bar charts.  Spreading a number
    // with the object path below destroys the values, so detect and pass through.
    const isNumericSeries =
        Array.isArray(rawSeries) &&
        rawSeries.length > 0 &&
        rawSeries.every((value) => typeof value === 'number');
    if (isNumericSeries) {
        return next as unknown as ApexOptions;
    }

    const series: Array<Record<string, unknown> & { data: unknown[] }> = Array.isArray(rawSeries)
        ? rawSeries
            .filter(Boolean)
            .map((entry) => {
                const seriesEntry = asRecord(entry);
                return {
                ...seriesEntry,
                data: Array.isArray(seriesEntry.data)
                    ? seriesEntry.data
                        .map((point) => normalizeSeriesPoint(point))
                        .filter((point) => point !== null)
                    : []
                };
            })
        : [];

    next.series = series;

    if (Array.isArray(next.yaxis)) {
        const seriesNames = new Set(series.map((entry) => entry.name).filter(Boolean));
        const normalizedYAxes = next.yaxis
            .map(asRecord)
            .filter((axis) => {
                if (!axis.seriesName) return true;
                if (Array.isArray(axis.seriesName)) {
                    return axis.seriesName.some((name) => seriesNames.has(name));
                }
                return seriesNames.has(axis.seriesName);
            })
            .map((axis) => ({ ...axis }));
        if (normalizedYAxes.length > 0) {
            next.yaxis = normalizedYAxes;
        } else {
            next.yaxis = undefined;
        }
    }

    if (next.annotations) {
        const annotations = asRecord(next.annotations);
        const xaxis = Array.isArray(annotations.xaxis) ? annotations.xaxis : [];
        next.annotations = {
            ...annotations,
            // Apex can crash on update cycles if any annotation buckets are missing.
            xaxis: xaxis.map(asRecord).filter((annotation) => {
                const x = Number(annotation.x);
                if (!Number.isFinite(x)) return false;
                if (
                    annotation.x2 !== undefined &&
                    annotation.x2 !== null &&
                    !Number.isFinite(Number(annotation.x2))
                ) return false;
                return true;
            }),
            yaxis: Array.isArray(annotations.yaxis) ? annotations.yaxis : [],
            points: Array.isArray(annotations.points) ? annotations.points : [],
            texts: Array.isArray(annotations.texts) ? annotations.texts : [],
            images: Array.isArray(annotations.images) ? annotations.images : [],
        };
    }

    if (next.stroke) {
        const stroke = asRecord(next.stroke);
        next.stroke = stroke;
        if (Array.isArray(stroke.width) && stroke.width.length !== series.length) {
            stroke.width = series.map((entry) => (entry.type === 'bar' ? 0 : 2));
        }
        if (Array.isArray(stroke.dashArray) && stroke.dashArray.length !== series.length) {
            stroke.dashArray = series.map(() => 0);
        }
    }

    if (next.fill) {
        const fill = asRecord(next.fill);
        next.fill = fill;
        if (Array.isArray(fill.type) && fill.type.length !== series.length) {
            fill.type = series.map((entry) => (entry.type === 'area' ? 'gradient' : 'solid'));
        }
    }

    if (!series.length) {
        next.series = [{ name: 'Series', type: 'line', data: [] }];
    }

    return next as unknown as ApexOptions;
}

export const chart: Action<HTMLElement, ApexOptions> = (node, options) => {
    const chartNode = node as ChartNode;
    let chartInstance: ApexInstance | null = null;
    let ApexChartsCtor: ApexConstructor | null = null;
    let pendingOptions = normalizeOptions(options);
    let destroyed = false;
    let initPromise: Promise<void> | null = null;

    async function init() {
        if (initPromise) return initPromise;
        initPromise = (async () => {
            // ApexCharts 6 keeps the legacy entry point as the full feature bundle.
            // Register only the renderers and optional UI used by YA-WAMF before
            // loading the slim core, keeping premium/authoring features out of the
            // route-only chart bundle.
            await Promise.all([
                import('apexcharts/line'),
                import('apexcharts/bar'),
                import('apexcharts/pie'),
                import('apexcharts/heatmap'),
                import('apexcharts/features/legend'),
                import('apexcharts/features/annotations'),
            ]);
            const mod: unknown = await import('apexcharts/core');
            if (destroyed) return;
            const ApexCharts = resolveApexConstructor(mod);
            ApexChartsCtor = ApexCharts;
            chartInstance = new ApexCharts(node, pendingOptions);
            await chartInstance.render();
            chartNode.__apexchart = chartInstance;
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
                let updatePromise: Promise<unknown>;
                try {
                    // updateOptions may throw synchronously on malformed intermediate states.
                    updatePromise = Promise.resolve(chartInstance.updateOptions(pendingOptions, true, true));
                } catch (syncError) {
                    updatePromise = Promise.reject(syncError);
                }
                void updatePromise
                    .catch(async (error: unknown) => {
                        console.error('Apex updateOptions failed, recreating chart instance', error);
                        if (destroyed || !ApexChartsCtor) return;
                        const existingChart = chartInstance;
                        try {
                            await existingChart?.destroy();
                        } catch {
                            // best effort cleanup
                        }
                        try {
                            chartInstance = new ApexChartsCtor(node, pendingOptions);
                            await chartInstance.render();
                            chartNode.__apexchart = chartInstance;
                        } catch (recreateError) {
                            chartInstance = null;
                            chartNode.__apexchart = null;
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
            chartNode.__apexchart = null;
        }
    };
};
