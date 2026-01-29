declare module 'svelte-apexcharts' {
    import { ApexOptions } from 'apexcharts';

    export interface ChartOptions {
        options?: ApexOptions;
        series?: ApexOptions['series'];
        type?: ApexOptions['chart']['type'];
        height?: string | number;
        width?: string | number;
    }

    export function chart(node: HTMLElement, options: ChartOptions): {
        update(options: ChartOptions): void;
        destroy(): void;
    };
}