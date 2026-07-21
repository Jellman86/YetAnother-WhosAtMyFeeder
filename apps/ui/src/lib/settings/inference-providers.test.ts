import { describe, expect, it } from 'vitest';
import type { ClassifierStatus } from '../api/classifier';
import {
    buildInferenceProviderChoices,
    getProviderPreferenceOrder,
} from './inference-providers';

const baseStatus: ClassifierStatus = {
    loaded: true,
    error: null,
    labels_count: 1,
    enabled: true,
};

describe('inference provider choices', () => {
    it('shows only packaged and host-available providers in backend priority order', () => {
        const status: ClassifierStatus = {
            ...baseStatus,
            image_flavor: 'intel',
            packaged_inference_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
            available_providers: ['intel_npu', 'intel_cpu', 'cpu', 'intel_gpu'],
            provider_preference_order: ['intel_npu', 'intel_cpu', 'cpu'],
            selected_provider: 'intel_npu',
            active_provider: 'intel_npu',
        };

        expect(buildInferenceProviderChoices(status, 'intel_npu')).toEqual([
            { value: 'auto', unavailable: false },
            { value: 'intel_npu', unavailable: false },
            { value: 'intel_cpu', unavailable: false },
            { value: 'cpu', unavailable: false },
            { value: 'intel_gpu', unavailable: false },
        ]);
        expect(getProviderPreferenceOrder(status)).toEqual(['intel_npu', 'intel_cpu', 'cpu']);
    });

    it('keeps a stale configured provider visible but disabled until it is replaced', () => {
        const status: ClassifierStatus = {
            ...baseStatus,
            image_flavor: 'intel',
            packaged_inference_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
            available_providers: ['intel_npu', 'intel_cpu', 'cpu'],
            provider_preference_order: ['intel_npu', 'intel_cpu', 'cpu'],
            selected_provider: 'cuda',
            active_provider: 'intel_npu',
        };

        expect(buildInferenceProviderChoices(status, 'cuda')).toEqual([
            { value: 'auto', unavailable: false },
            { value: 'intel_npu', unavailable: false },
            { value: 'intel_cpu', unavailable: false },
            { value: 'cpu', unavailable: false },
            { value: 'cuda', unavailable: true },
        ]);
    });

    it('fails closed when live capabilities cannot be loaded', () => {
        expect(buildInferenceProviderChoices(null, 'intel_gpu')).toEqual([
            { value: 'auto', unavailable: false },
            { value: 'intel_gpu', unavailable: true },
        ]);
        expect(buildInferenceProviderChoices(null, 'auto')).toEqual([
            { value: 'auto', unavailable: false },
        ]);
    });
});
