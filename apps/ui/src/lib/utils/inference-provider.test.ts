import { describe, expect, it } from 'vitest';
import { classifyInferenceProvider } from './inference-provider';

describe('classifyInferenceProvider', () => {
    it('classifies intel gpu as gpu', () => {
        expect(classifyInferenceProvider('intel_gpu', 'openvino')).toEqual({
            kind: 'gpu',
            label: 'GPU'
        });
    });

    it('classifies cpu provider as cpu', () => {
        expect(classifyInferenceProvider('intel_cpu', 'openvino')).toEqual({
            kind: 'cpu',
            label: 'CPU'
        });
    });

    it('falls back to backend when provider is missing', () => {
        expect(classifyInferenceProvider(null, 'tflite')).toEqual({
            kind: 'cpu',
            label: 'CPU'
        });
    });

    it('returns null kind for unknown values', () => {
        expect(classifyInferenceProvider('mystery', 'mystery')).toEqual({
            kind: null,
            label: 'Unknown'
        });
    });
});
