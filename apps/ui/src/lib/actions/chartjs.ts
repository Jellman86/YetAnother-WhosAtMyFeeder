import type { Chart, ChartConfiguration, ChartType } from 'chart.js';

import { whenNearViewport } from './near-viewport';

export type CanvasChartConfig =
    | ChartConfiguration<'line', number[], string>
    | ChartConfiguration<'bar', number[], string>
    | ChartConfiguration<'doughnut', number[], string>;
export type MixedCanvasChartConfig = ChartConfiguration<'bar' | 'line', number[], string>;
type ChartCanvas = HTMLCanvasElement & { __chartjs?: Chart | null };

/** Toggle a doughnut slice from a semantic, keyboard-operable HTML legend. */
export function toggleChartSlice(node: HTMLCanvasElement | null, index: number): boolean | null {
    const instance = (node as ChartCanvas | null)?.__chartjs;
    if (!instance) return null;
    instance.toggleDataVisibility(index);
    instance.update();
    return instance.getDataVisibility(index);
}

/** Keep Chart.js off pages without charts and release its canvas on Svelte teardown. */
export function chartjs(node: HTMLCanvasElement, initialConfig: CanvasChartConfig | MixedCanvasChartConfig) {
    const chartNode = node as ChartCanvas;
    let instance: Chart | null = null;
    let revision = 0;
    let destroyed = false;

    async function render(config: CanvasChartConfig | MixedCanvasChartConfig) {
        const currentRevision = ++revision;
        const { default: ChartConstructor } = await import('./chartjs-runtime');
        if (destroyed || currentRevision !== revision) return;
        instance?.destroy();
        instance = new ChartConstructor(node, config as ChartConfiguration<ChartType, number[], string>);
        chartNode.__chartjs = instance;
    }

    void render(initialConfig);
    return {
        update(config: CanvasChartConfig | MixedCanvasChartConfig) {
            void render(config);
        },
        destroy() {
            destroyed = true;
            revision += 1;
            instance?.destroy();
            instance = null;
            chartNode.__chartjs = null;
        },
    };
}

/**
 * The same chart, drawn when its canvas first comes near the viewport. A long page keeps the chart
 * library and the drawing work off its first paint for charts nobody has scrolled to yet.
 */
export function chartjsWhenNear(node: HTMLCanvasElement, initialConfig: CanvasChartConfig | MixedCanvasChartConfig) {
    let latestConfig = initialConfig;
    let chart: ReturnType<typeof chartjs> | null = null;
    const watcher = whenNearViewport(node, () => {
        chart = chartjs(node, latestConfig);
    });
    return {
        update(config: CanvasChartConfig | MixedCanvasChartConfig) {
            latestConfig = config;
            chart?.update(config);
        },
        destroy() {
            watcher.destroy();
            chart?.destroy();
        },
    };
}
