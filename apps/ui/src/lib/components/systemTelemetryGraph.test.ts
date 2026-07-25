import { describe, expect, it } from 'vitest';

import { appendTelemetrySample, telemetryPolyline, type TelemetryPoint } from './systemTelemetryGraph';

describe('system telemetry graph helpers', () => {
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

    it('maps bounded utilization values into SVG coordinates without inventing zeroes', () => {
        const points: TelemetryPoint[] = [
            { cpu: 0, accelerator: null, acceleratorLabel: 'NPU' },
            { cpu: 50, accelerator: 25, acceleratorLabel: 'NPU' },
            { cpu: 100, accelerator: 75, acceleratorLabel: 'NPU' }
        ];

        expect(telemetryPolyline(points, 'cpu')).toBe('0,100 50,50 100,0');
        expect(telemetryPolyline(points, 'accelerator')).toBe('50,75 100,25');
    });
});
