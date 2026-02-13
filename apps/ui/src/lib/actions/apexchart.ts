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

    void init().catch((error: unknown) => {
        // Prevent unhandled promise rejections when Apex fails initial render.
        console.error('Apex initial render failed', error);
    });

    return {
        update(newOptions) {
            pendingOptions = newOptions;
            if (chartInstance) {
                void Promise
                    .resolve(chartInstance.updateOptions(newOptions, true, true))
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
