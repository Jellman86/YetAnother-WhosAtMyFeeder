import { beforeEach, describe, expect, it, vi } from 'vitest';

const apex = vi.hoisted(() => ({
    constructor: vi.fn(),
    destroy: vi.fn(),
    render: vi.fn(() => Promise.resolve()),
    updateOptions: vi.fn((_options: unknown, _redrawPaths: boolean, _animate: boolean) =>
        Promise.resolve()),
}));

const registrations = vi.hoisted(() => ({
    annotations: 0,
    bar: 0,
    heatmap: 0,
    legend: 0,
    line: 0,
    pie: 0,
}));

vi.mock('apexcharts/line', () => { registrations.line += 1; return {}; });
vi.mock('apexcharts/bar', () => { registrations.bar += 1; return {}; });
vi.mock('apexcharts/pie', () => { registrations.pie += 1; return {}; });
vi.mock('apexcharts/heatmap', () => { registrations.heatmap += 1; return {}; });
vi.mock('apexcharts/features/legend', () => { registrations.legend += 1; return {}; });
vi.mock('apexcharts/features/annotations', () => { registrations.annotations += 1; return {}; });

vi.mock('apexcharts/core', () => ({
    default: class ApexChartsCoreMock {
        constructor(node: HTMLElement, options: unknown) {
            apex.constructor(node, options);
        }

        render() {
            return apex.render();
        }

        updateOptions(options: unknown, redrawPaths: boolean, animate: boolean) {
            return apex.updateOptions(options, redrawPaths, animate);
        }

        destroy() {
            apex.destroy();
        }
    },
}));

import { chart } from './apexchart';

describe('chart action', () => {
    beforeEach(() => {
        apex.constructor.mockClear();
        apex.destroy.mockClear();
        apex.render.mockClear();
        apex.updateOptions.mockClear();
    });

    it('loads the ApexCharts slim core and preserves its update lifecycle', async () => {
        const node = {} as HTMLElement;
        const action = chart(node, {
            chart: { type: 'line' },
            series: [{ name: 'Visits', data: [1, 2, 3] }],
        });

        await vi.waitFor(() => expect(apex.render).toHaveBeenCalledOnce());
        expect(registrations).toEqual({
            annotations: 1,
            bar: 1,
            heatmap: 1,
            legend: 1,
            line: 1,
            pie: 1,
        });
        expect(apex.constructor).toHaveBeenCalledWith(
            node,
            expect.objectContaining({
                series: [{ name: 'Visits', data: [1, 2, 3] }],
            }),
        );

        action?.update?.({
            chart: { type: 'line' },
            series: [{ name: 'Visits', data: [4, 5] }],
        });
        await vi.waitFor(() => expect(apex.updateOptions).toHaveBeenCalledOnce());
        expect(apex.updateOptions).toHaveBeenCalledWith(
            expect.objectContaining({
                series: [{ name: 'Visits', data: [4, 5] }],
            }),
            true,
            true,
        );

        action?.destroy?.();
        expect(apex.destroy).toHaveBeenCalledOnce();
    });
});
