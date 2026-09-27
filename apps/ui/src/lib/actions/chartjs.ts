import type { Chart, ChartConfiguration, ChartType } from 'chart.js';

export type CanvasChartConfig =
    | ChartConfiguration<'line', number[], string>
    | ChartConfiguration<'bar', number[], string>
    | ChartConfiguration<'doughnut', number[], string>;
type ChartCanvas = HTMLCanvasElement & { __chartjs?: Chart | null };

/** Keep Chart.js off pages without charts and release its canvas on Svelte teardown. */
export function chartjs(node: HTMLCanvasElement, initialConfig: CanvasChartConfig) {
    const chartNode = node as ChartCanvas;
    let instance: Chart | null = null;
    let revision = 0;
    let destroyed = false;

    async function render(config: CanvasChartConfig) {
        const currentRevision = ++revision;
        const { default: ChartConstructor } = await import('chart.js/auto');
        if (destroyed || currentRevision !== revision) return;
        instance?.destroy();
        instance = new ChartConstructor(node, config as ChartConfiguration<ChartType, number[], string>);
        chartNode.__chartjs = instance;
    }

    void render(initialConfig);
    return {
        update(config: CanvasChartConfig) {
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
