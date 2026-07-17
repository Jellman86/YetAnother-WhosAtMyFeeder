import { describe, expect, it } from 'vitest';

import { pickFastestProvider } from './device_optimize';
import type { DeviceMatrix } from '../../api/model_eval';

function matrix(devices: Record<string, unknown>): DeviceMatrix {
    return {
        run_id: 'r1',
        generated_at: '2026-07-17T00:00:00Z',
        devices: Object.keys(devices),
        models: { small_birds: { devices: devices as never } }
    };
}

describe('pickFastestProvider', () => {
    it('picks the fastest device that passed and agrees with CPU', () => {
        const m = matrix({
            CPU: { compiles: true, finite: true, latency_ms: 120 },
            GPU: { compiles: true, finite: true, matches_cpu: true, latency_ms: 40 },
            NPU: { compiles: true, finite: true, matches_cpu: true, latency_ms: 65 }
        });
        expect(pickFastestProvider(m, 'small_birds')).toEqual({ device: 'GPU', provider: 'intel_gpu', latencyMs: 40 });
    });

    it('excludes an accelerator that disagrees with CPU even if faster', () => {
        const m = matrix({
            CPU: { compiles: true, finite: true, latency_ms: 120 },
            GPU: { compiles: true, finite: true, matches_cpu: false, latency_ms: 20 }
        });
        expect(pickFastestProvider(m, 'small_birds')).toEqual({ device: 'CPU', provider: 'intel_cpu', latencyMs: 120 });
    });

    it('excludes a device that produced non-finite output', () => {
        const m = matrix({
            CPU: { compiles: true, finite: true, latency_ms: 120 },
            NPU: { compiles: true, finite: false, matches_cpu: true, latency_ms: 30 }
        });
        expect(pickFastestProvider(m, 'small_birds')?.device).toBe('CPU');
    });

    it('excludes a device that did not compile', () => {
        const m = matrix({
            GPU: { compiles: false, latency_ms: 10 },
            CPU: { compiles: true, finite: true, latency_ms: 90 }
        });
        expect(pickFastestProvider(m, 'small_birds')?.provider).toBe('intel_cpu');
    });

    it('handles suffixed device names like GPU.0', () => {
        const m = matrix({
            CPU: { compiles: true, finite: true, latency_ms: 120 },
            'GPU.0': { compiles: true, finite: true, matches_cpu: true, latency_ms: 45 }
        });
        expect(pickFastestProvider(m, 'small_birds')).toEqual({ device: 'GPU', provider: 'intel_gpu', latencyMs: 45 });
    });

    it('returns null when the model is absent or has no devices', () => {
        expect(pickFastestProvider(null, 'small_birds')).toBeNull();
        expect(pickFastestProvider(matrix({}), 'small_birds')).toBeNull();
        expect(pickFastestProvider(matrix({ CPU: { compiles: true, finite: true, latency_ms: 100 } }), 'other')).toBeNull();
    });
});
