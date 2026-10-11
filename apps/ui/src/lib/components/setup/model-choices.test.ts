import { describe, expect, it } from 'vitest';
import { feederCoordinates, validationRecommendation } from './model-choices';
import type { DeviceMatrix, ModelEvalModelSummary } from '../../api/model_eval';

describe('wizard feeder coordinates', () => {
    it('distinguishes an absent location from the equator and prime meridian', () => {
        expect(feederCoordinates('', ' ')).toEqual({ latitude: null, longitude: null, error: null });
        expect(feederCoordinates('0', '0')).toEqual({ latitude: 0, longitude: 0, error: null });
    });

    it('requires a complete pair', () => {
        expect(feederCoordinates('0', '').error).toBe('incomplete');
        expect(feederCoordinates('', '0').error).toBe('incomplete');
    });

    it.each([['91', '0'], ['0', '-181'], ['NaN', '0'], ['0', 'Infinity'], ['12junk', '20']])('rejects invalid coordinates %s,%s', (lat, lon) => {
        expect(feederCoordinates(lat, lon).error).toBe('range');
    });

    it('accepts valid bounds and trims whitespace', () => {
        expect(feederCoordinates(' -90 ', '180')).toEqual({ latitude: -90, longitude: 180, error: null });
    });
});

describe('wizard validation recommendation', () => {
    const summary: ModelEvalModelSummary = {
        model_id: 'bird', ready: true, active_provider: 'cpu', p50_latency_ms: 999,
        validated_providers: ['cpu', 'intel_npu'], warnings: [],
        images_evaluated: 24, top1_accuracy: 0, top3_accuracy: 0, top5_accuracy: 0,
        abstention_rate: 0, high_confidence_unknown_rate: 0, shared_core_top1: 0, regional_top1: 0
    };
    const matrix: DeviceMatrix = {
        run_id: 'run', generated_at: '', devices: ['cpu', 'intel_npu'], models: {
            bird: { best_provider: 'intel_npu', providers: {
                cpu: { ok: true, compiles: true, baseline: true },
                intel_npu: { ok: true, compiles: true, finite: true, latency_ms: 42 }
            } }
        }
    };

    it('uses the measured matrix recommendation and median over a legacy summary field', () => {
        expect(validationRecommendation('bird', summary, matrix)).toEqual({ provider: 'intel_npu', medianMs: 42, providers: ['cpu', 'intel_npu'] });
    });

    it('never recommends a provider that failed or produced nonfinite output', () => {
        const bad: DeviceMatrix = { ...matrix, models: { bird: { best_provider: 'intel_npu', providers: {
            cpu: { ok: true, compiles: true }, intel_npu: { ok: true, compiles: true, finite: false }
        } } } };
        expect(validationRecommendation('bird', summary, bad)).toEqual({ provider: null, medianMs: null, providers: ['cpu'] });
    });

    it('supports an older run with only the compatibility summary', () => {
        expect(validationRecommendation('bird', summary, null)).toEqual({ provider: 'cpu', medianMs: 999, providers: ['cpu', 'intel_npu'] });
    });

    it('does not borrow results for a different model or a critical failure', () => {
        expect(validationRecommendation('other', undefined, matrix).providers).toEqual([]);
        expect(validationRecommendation('bird', { ...summary, warnings: [{ severity: 'critical', code: 'failed', message: 'failed' }] }, null).provider).toBeNull();
    });
});
