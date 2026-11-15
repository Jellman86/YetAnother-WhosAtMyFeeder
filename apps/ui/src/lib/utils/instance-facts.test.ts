import { describe, expect, it } from 'vitest';

import { describeRuntime, startedAtFrom } from './instance-facts';

describe('what the About page says this instance runs on', () => {
    it('names the runtime and the device it runs on, not a bare runtime token', () => {
        expect(describeRuntime({ inference_backend: 'tflite', active_provider: 'cpu' })).toEqual({ runtime: 'TFLite', device: 'CPU' });
        expect(describeRuntime({ inference_backend: 'openvino', active_provider: 'intel_gpu' })).toEqual({ runtime: 'OpenVINO', device: 'Intel GPU' });
        expect(describeRuntime({ inference_backend: 'openvino', active_provider: 'intel_npu' })).toEqual({ runtime: 'OpenVINO', device: 'Intel NPU' });
        expect(describeRuntime({ inference_backend: 'onnxruntime', active_provider: 'cuda' })).toEqual({ runtime: 'ONNX Runtime', device: 'NVIDIA GPU' });
    });

    it('claims no device it was not told about', () => {
        expect(describeRuntime({ inference_backend: 'tflite', active_provider: null })).toEqual({ runtime: 'TFLite', device: null });
        expect(describeRuntime({ inference_backend: null, active_provider: 'auto' })).toBeNull();
        expect(describeRuntime(null)).toBeNull();
    });

    it('passes an unrecognised runtime through as reported', () => {
        expect(describeRuntime({ inference_backend: 'newthing', active_provider: 'cpu' })).toEqual({ runtime: 'newthing', device: 'CPU' });
    });
});

describe('when this process started', () => {
    it('reads the first valid start time among the sources', () => {
        expect(startedAtFrom(undefined, { startup_started_at: '2026-11-15T06:00:00Z' })).toBe('2026-11-15T06:00:00Z');
        expect(startedAtFrom({ startup_started_at: '2026-11-15T05:00:00Z' }, { startup_started_at: '2026-11-15T06:00:00Z' })).toBe('2026-11-15T05:00:00Z');
    });

    it('is unmeasured, never guessed, when no source has a valid time', () => {
        expect(startedAtFrom(null, undefined)).toBeNull();
        expect(startedAtFrom({ startup_started_at: null }, { startup_started_at: 'not a date' })).toBeNull();
    });
});
