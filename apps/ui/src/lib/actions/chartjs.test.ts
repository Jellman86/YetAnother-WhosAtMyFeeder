import { beforeEach, describe, expect, it, vi } from 'vitest';

const chartMock = vi.hoisted(() => ({
    construct: vi.fn(),
    destroy: vi.fn(),
}));

vi.mock('chart.js/auto', () => ({
    default: class ChartMock {
        constructor(node: HTMLCanvasElement, config: unknown) {
            chartMock.construct(node, config);
        }
        destroy() {
            chartMock.destroy();
        }
    },
}));

import { chartjs, type CanvasChartConfig } from './chartjs';

const initial: CanvasChartConfig = { type: 'bar', data: { labels: ['Mon'], datasets: [{ data: [2] }] } };
const updated: CanvasChartConfig = { type: 'bar', data: { labels: ['Tue'], datasets: [{ data: [3] }] } };

describe('Chart.js action', () => {
    beforeEach(() => {
        chartMock.construct.mockClear();
        chartMock.destroy.mockClear();
    });

    it('replaces the chart on update and releases the canvas on teardown', async () => {
        const canvas = {} as HTMLCanvasElement;
        const action = chartjs(canvas, initial);
        await vi.waitFor(() => expect(chartMock.construct).toHaveBeenCalledWith(canvas, initial));

        action.update(updated);
        await vi.waitFor(() => expect(chartMock.construct).toHaveBeenCalledWith(canvas, updated));
        expect(chartMock.destroy).toHaveBeenCalledTimes(1);

        action.destroy();
        expect(chartMock.destroy).toHaveBeenCalledTimes(2);
    });

    it('does not mount a chart after the node is destroyed', async () => {
        const action = chartjs({} as HTMLCanvasElement, initial);
        action.destroy();
        await Promise.resolve();
        expect(chartMock.construct).not.toHaveBeenCalled();
    });
});
