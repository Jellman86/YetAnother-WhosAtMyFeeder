import type { Action } from 'svelte/action';
import type { ApexOptions } from 'apexcharts';

type ApexModule = typeof import('apexcharts');

export const chart: Action<HTMLElement, ApexOptions> = (node, options) => {
    let chartInstance: any = null;
    let ApexChartsCtor: any = null;
    let pendingOptions = options;
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

    void init();

    return {
        update(newOptions) {
            pendingOptions = newOptions;
            if (chartInstance) {
                Promise
                    .resolve(chartInstance.updateOptions(newOptions, true, true))
                    .catch(async (error: unknown) => {
                        console.error('Apex updateOptions failed, recreating chart instance', error);
                        if (destroyed || !ApexChartsCtor) return;
                        try {
                            await chartInstance.destroy();
                        } catch {
                            // best effort cleanup
                        }
                        chartInstance = new ApexChartsCtor(node, pendingOptions);
                        await chartInstance.render();
                        (node as any).__apexchart = chartInstance;
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
