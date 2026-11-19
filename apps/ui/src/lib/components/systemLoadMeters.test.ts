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
        const meters = loadMeters({ cpu: 95.4, accelerator: 25, acceleratorLabel: 'NPU' }, 'CPU');

        expect(meters).toEqual([
            { id: 'cpu', label: 'CPU', percent: 95.4, shown: '95%', fill: CPU_STYLE.fill },
            { id: 'accelerator', label: 'NPU', percent: 25, shown: '25%', fill: PRIMARY_ACCELERATOR_STYLE.fill }
        ]);
    });

    it('leaves out a reading that was not taken rather than drawing an empty meter as zero', () => {
        expect(loadMeters({ cpu: 12, accelerator: null, acceleratorLabel: 'NPU' }, 'CPU').map((meter) => meter.id)).toEqual(['cpu']);
        expect(loadMeters({ cpu: null, accelerator: 40, acceleratorLabel: 'Intel GPU' }, 'CPU').map((meter) => meter.label)).toEqual(['Intel GPU']);
        expect(loadMeters({ cpu: 0, accelerator: null, acceleratorLabel: null }, 'CPU')[0]?.shown).toBe('0%');
        expect(loadMeters(undefined, 'CPU')).toEqual([]);
    });
});
