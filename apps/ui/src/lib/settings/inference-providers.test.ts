import { describe, expect, it } from 'vitest';
import type { ClassifierStatus } from '../api/classifier';
import {
    buildInferenceProviderChoices,
    getProviderPreferenceOrder,
    getRuntimeProviderOrder,
    inferenceProviderForSave,
    parseInferenceProvider,
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
            host_available_providers: ['intel_npu', 'intel_cpu', 'cpu', 'intel_gpu'],
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
        expect(getRuntimeProviderOrder(status, ['intel_npu', 'intel_cpu', 'cpu'])).toEqual([
            'intel_npu',
            'intel_cpu',
            'cpu',
        ]);
    });

    it('does not present available manual alternatives as automatic fallbacks', () => {
        const status: ClassifierStatus = {
            ...baseStatus,
            available_providers: ['intel_npu', 'intel_gpu', 'intel_cpu', 'cpu'],
            provider_preference_order: ['intel_npu', 'intel_cpu', 'cpu'],
            active_provider: 'intel_npu',
        };

        expect(getRuntimeProviderOrder(status, ['intel_npu', 'intel_gpu', 'intel_cpu', 'cpu'])).toEqual([
            'intel_npu',
            'intel_cpu',
            'cpu',
        ]);
    });

    it('keeps the live provider visible when installed metadata is stale', () => {
        const status: ClassifierStatus = {
            ...baseStatus,
            available_providers: ['intel_npu', 'intel_cpu', 'cpu'],
            provider_preference_order: ['intel_npu', 'intel_cpu', 'cpu'],
            active_provider: 'intel_npu',
        };

        expect(getRuntimeProviderOrder(status, ['intel_cpu', 'cpu'])).toEqual([
            'intel_npu',
            'intel_cpu',
            'cpu',
        ]);
    });

    it('shows only the known active provider when an older backend omits its runtime order', () => {
        const status: ClassifierStatus = {
            ...baseStatus,
            available_providers: ['intel_npu', 'intel_cpu', 'cpu'],
            active_provider: 'intel_npu',
        };

        expect(getRuntimeProviderOrder(status, ['intel_npu', 'intel_cpu', 'cpu'])).toEqual(['intel_npu']);
    });

    it('uses host capabilities and the prospective model contract during setup', () => {
        const status: ClassifierStatus = {
            ...baseStatus,
            image_flavor: 'intel',
            packaged_inference_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
            host_available_providers: ['intel_gpu', 'intel_cpu', 'cpu', 'intel_npu'],
            available_providers: ['intel_gpu', 'intel_cpu', 'cpu'],
            provider_preference_order: ['intel_gpu', 'intel_cpu', 'cpu'],
            selected_provider: 'auto',
            active_provider: 'intel_gpu',
        };

        expect(buildInferenceProviderChoices(status, 'auto', ['intel_npu', 'intel_cpu', 'cpu'])).toEqual([
            { value: 'auto', unavailable: false },
            { value: 'intel_cpu', unavailable: false },
            { value: 'cpu', unavailable: false },
            { value: 'intel_npu', unavailable: false },
        ]);
    });

    it('offers only providers that passed validation for the prospective model', () => {
        const status: ClassifierStatus = {
            ...baseStatus,
            image_flavor: 'full',
            packaged_inference_providers: ['cpu', 'cuda', 'intel_cpu'],
            host_available_providers: ['cuda', 'intel_cpu', 'cpu'],
            available_providers: ['cuda', 'intel_cpu', 'cpu'],
        };

        expect(buildInferenceProviderChoices(
            status,
            'auto',
            ['cpu', 'cuda', 'intel_cpu'],
            ['cpu', 'cuda'],
        )).toEqual([
            { value: 'auto', unavailable: false },
            { value: 'cuda', unavailable: false },
            { value: 'cpu', unavailable: false },
        ]);
    });

    it('orders a prospective model by its own measured install preference', () => {
        const status: ClassifierStatus = {
            ...baseStatus,
            image_flavor: 'intel',
            packaged_inference_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
            host_available_providers: ['intel_gpu', 'intel_cpu', 'cpu', 'intel_npu'],
            available_providers: ['intel_cpu', 'cpu'],
        };

        expect(buildInferenceProviderChoices(
            status,
            'auto',
            ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
            ['intel_cpu', 'intel_gpu', 'intel_npu'],
            ['intel_npu', 'intel_gpu', 'intel_cpu'],
        )).toEqual([
            { value: 'auto', unavailable: false },
            { value: 'intel_npu', unavailable: false },
            { value: 'intel_gpu', unavailable: false },
            { value: 'intel_cpu', unavailable: false },
        ]);
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

describe('saved inference provider preservation', () => {
    it('recognises every provider the settings API accepts, including Intel NPU', () => {
        for (const provider of ['auto', 'cpu', 'cuda', 'intel_gpu', 'intel_cpu', 'intel_npu']) {
            expect(parseInferenceProvider(provider)).toBe(provider);
        }
    });

    it('does not mistake a missing or unrecognised value for a provider', () => {
        for (const value of [undefined, null, '', 'Intel_NPU', ' intel_npu', 'rocm', 42]) {
            expect(parseInferenceProvider(value)).toBeNull();
        }
    });

    it('writes a saved Intel NPU choice back unchanged on an unrelated settings save', () => {
        const stored = 'intel_npu';
        const form = parseInferenceProvider(stored) ?? 'auto';

        expect(inferenceProviderForSave(form, stored)).toBe('intel_npu');
    });

    it('sends the form value when the stored value is known or absent', () => {
        expect(inferenceProviderForSave('cpu', 'intel_npu')).toBe('cpu');
        expect(inferenceProviderForSave('auto', 'intel_npu')).toBe('auto');
        expect(inferenceProviderForSave('intel_npu', 'auto')).toBe('intel_npu');
        expect(inferenceProviderForSave('auto', undefined)).toBe('auto');
        expect(inferenceProviderForSave('auto', null)).toBe('auto');
    });

    it('leaves an unrecognised stored value untouched instead of rewriting it to Auto', () => {
        expect(inferenceProviderForSave('auto', 'Intel_NPU')).toBeUndefined();
        expect(inferenceProviderForSave('auto', 'rocm')).toBeUndefined();
        expect(inferenceProviderForSave('intel_cpu', 'rocm')).toBe('intel_cpu');
    });
});
