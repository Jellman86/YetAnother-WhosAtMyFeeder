import { describe, expect, it } from 'vitest';

import { appendTelemetrySample, loadMeters, type TelemetryPoint } from './systemLoadMeters';
import { CPU_STYLE, PRIMARY_ACCELERATOR_STYLE } from '../utils/system-history';

describe('the sidebar load meters', () => {
    it('keeps a bounded rolling history and retains all-null baseline samples', () => {
        const initial = appendTelemetrySample([], {
            sampled_at: '2026-07-25T11:59:58Z',
            cpu_percent: null,
            accelerator: { kind: 'gpu', label: 'Intel GPU', utilization_percent: null }
        });
        expect(initial).toEqual([{ cpu: null, accelerator: null, acceleratorLabel: 'Intel GPU' }]);

        const existing: TelemetryPoint[] = Array.from({ length: 25 }, (_, index) => ({
            cpu: index,
            accelerator: index / 2,
            acceleratorLabel: 'NPU'
        }));

        const afterNull = appendTelemetrySample(existing, {
            sampled_at: '2026-07-25T12:00:00Z',
            cpu_percent: null,
            accelerator: { kind: 'npu', label: 'NPU', utilization_percent: null }
        });
        expect(afterNull).toHaveLength(25);
        expect(afterNull.at(-1)).toEqual({ cpu: null, accelerator: null, acceleratorLabel: 'NPU' });

        const updated = appendTelemetrySample(afterNull, {
            sampled_at: '2026-07-25T12:00:02Z',
            cpu_percent: 48.2,
            accelerator: { kind: 'npu', label: 'NPU', utilization_percent: 17.1 }
        });
        expect(updated).toHaveLength(25);
        expect(updated[0]?.cpu).toBe(2);
        expect(updated.at(-1)).toEqual({ cpu: 48.2, accelerator: 17.1, acceleratorLabel: 'NPU' });
    });

    it('gives the CPU and the accelerator a meter each, in the Health chart\'s colours', () => {
        const meters = loadMeters([{ cpu: 95.4, accelerator: 25, acceleratorLabel: 'NPU' }], 'CPU', 'Not measured');

        expect(meters).toEqual([
            { id: 'cpu', label: 'CPU', measured: true, percent: 95.4, shown: '95%', fill: CPU_STYLE.fill },
            { id: 'accelerator', label: 'NPU', measured: true, percent: 25, shown: '25%', fill: PRIMARY_ACCELERATOR_STYLE.fill }
        ]);
    });

    it('shows a detected accelerator as Not measured before its first numeric reading and distinguishes it from 0% (#1088)', () => {
        expect(loadMeters([], 'CPU', 'Not measured')).toEqual([]);

        // First sample: CPU measured, Intel GPU detected with null utilization.
        const initial = loadMeters([{ cpu: 19, accelerator: null, acceleratorLabel: 'Intel GPU' }], 'CPU', 'Not measured');
        expect(initial).toEqual([
            { id: 'cpu', label: 'CPU', measured: true, percent: 19, shown: '19%', fill: CPU_STYLE.fill },
            { id: 'accelerator', label: 'Intel GPU', measured: false, percent: 0, shown: 'Not measured', fill: PRIMARY_ACCELERATOR_STYLE.fill }
        ]);

        // First all-null baseline sample: both CPU and detected accelerator show Not measured.
        const baseline = loadMeters([{ cpu: null, accelerator: null, acceleratorLabel: 'NPU' }], 'CPU', 'Not measured');
        expect(baseline).toEqual([
            { id: 'cpu', label: 'CPU', measured: false, percent: 0, shown: 'Not measured', fill: CPU_STYLE.fill },
            { id: 'accelerator', label: 'NPU', measured: false, percent: 0, shown: 'Not measured', fill: PRIMARY_ACCELERATOR_STYLE.fill }
        ]);

        // Measured 0% is distinct from Not measured.
        const idle = loadMeters([{ cpu: 0, accelerator: 0, acceleratorLabel: 'Intel GPU' }], 'CPU', 'Not measured');
        expect(idle).toEqual([
            { id: 'cpu', label: 'CPU', measured: true, percent: 0, shown: '0%', fill: CPU_STYLE.fill },
            { id: 'accelerator', label: 'Intel GPU', measured: true, percent: 0, shown: '0%', fill: PRIMARY_ACCELERATOR_STYLE.fill }
        ]);

        // CPU-only host shows CPU without an accelerator row.
        expect(loadMeters([{ cpu: 12, accelerator: null, acceleratorLabel: null }], 'CPU', 'Not measured').map((meter) => meter.label)).toEqual(['CPU']);
    });

    it('tracks transitions across null -> 0 -> positive -> null and primary identity changes', () => {
        const sequence: TelemetryPoint[] = [
            { cpu: 20, accelerator: null, acceleratorLabel: 'Intel GPU' },
            { cpu: 21, accelerator: 0, acceleratorLabel: 'Intel GPU' },
            { cpu: 22, accelerator: 34, acceleratorLabel: 'Intel GPU' },
            { cpu: 23, accelerator: null, acceleratorLabel: 'Intel GPU' }
        ];
        expect(loadMeters(sequence.slice(0, 1), 'CPU', 'Not measured')[1]).toMatchObject({ label: 'Intel GPU', measured: false, shown: 'Not measured' });
        expect(loadMeters(sequence.slice(0, 2), 'CPU', 'Not measured')[1]).toMatchObject({ label: 'Intel GPU', measured: true, shown: '0%' });
        expect(loadMeters(sequence.slice(0, 3), 'CPU', 'Not measured')[1]).toMatchObject({ label: 'Intel GPU', measured: true, shown: '34%' });
        expect(loadMeters(sequence, 'CPU', 'Not measured')[1]).toMatchObject({ label: 'Intel GPU', measured: false, percent: 0, shown: 'Not measured' });

        // Primary switches to NPU, then disappears.
        const switched = loadMeters([...sequence, { cpu: 24, accelerator: 12, acceleratorLabel: 'NPU' }], 'CPU', 'Not measured');
        expect(switched[1]).toMatchObject({ label: 'NPU', measured: true, shown: '12%' });

        const removed = loadMeters([...sequence, { cpu: 25, accelerator: null, acceleratorLabel: null }], 'CPU', 'Not measured');
        expect(removed.map((meter) => meter.id)).toEqual(['cpu']);
    });
});
