import { describe, expect, it } from 'vitest';

import { appendTelemetrySample, loadMeters, type TelemetryPoint } from './systemLoadMeters';
import { CPU_STYLE, PRIMARY_ACCELERATOR_STYLE } from '../utils/system-history';

describe('the sidebar load meters', () => {
    it('keeps a bounded rolling history and ignores empty baseline samples', () => {
        const existing: TelemetryPoint[] = Array.from({ length: 25 }, (_, index) => ({
            cpu: index,
            accelerator: index / 2,
            acceleratorLabel: 'NPU'
        }));

        const unchanged = appendTelemetrySample(existing, {
            sampled_at: '2026-07-25T12:00:00Z',
            cpu_percent: null,
            accelerator: { kind: 'npu', label: 'NPU', utilization_percent: null }
        });
        expect(unchanged).toBe(existing);

        const updated = appendTelemetrySample(existing, {
            sampled_at: '2026-07-25T12:00:02Z',
            cpu_percent: 48.2,
            accelerator: { kind: 'npu', label: 'NPU', utilization_percent: 17.1 }
        });
        expect(updated).toHaveLength(25);
        expect(updated[0]?.cpu).toBe(1);
        expect(updated.at(-1)).toEqual({ cpu: 48.2, accelerator: 17.1, acceleratorLabel: 'NPU' });
    });

    it('gives the CPU and the accelerator a meter each, in the Health chart\'s colours', () => {
        const meters = loadMeters([{ cpu: 95.4, accelerator: 25, acceleratorLabel: 'NPU' }], 'CPU', 'Not measured');

        expect(meters).toEqual([
            { id: 'cpu', label: 'CPU', measured: true, percent: 95.4, shown: '95%', fill: CPU_STYLE.fill },
            { id: 'accelerator', label: 'NPU', measured: true, percent: 25, shown: '25%', fill: PRIMARY_ACCELERATOR_STYLE.fill }
        ]);
    });

    it('gives no meter to a device no sample has read, rather than drawing an empty one as zero', () => {
        const ids = (history: TelemetryPoint[]) => loadMeters(history, 'CPU', 'Not measured').map((meter) => meter.label);
        expect(ids([{ cpu: 12, accelerator: null, acceleratorLabel: 'NPU' }])).toEqual(['CPU']);
        expect(ids([{ cpu: null, accelerator: 40, acceleratorLabel: 'Intel GPU' }])).toEqual(['Intel GPU']);
        expect(loadMeters([{ cpu: 0, accelerator: null, acceleratorLabel: null }], 'CPU', 'Not measured')[0]?.shown).toBe('0%');
        expect(loadMeters([], 'CPU', 'Not measured')).toEqual([]);
    });

    it('keeps a meter through a missed sample, said not measured, so the card does not jump', () => {
        const history: TelemetryPoint[] = [
            { cpu: 40, accelerator: 25, acceleratorLabel: 'NPU' },
            { cpu: 41, accelerator: null, acceleratorLabel: 'NPU' }
        ];
        const [cpu, npu] = loadMeters(history, 'CPU', 'Not measured');

        expect(cpu).toMatchObject({ measured: true, shown: '41%' });
        // The row stays where it was, empty and in words, never passed off as the last figure or as 0%.
        expect(npu).toMatchObject({ id: 'accelerator', label: 'NPU', measured: false, percent: 0, shown: 'Not measured' });
    });
});
