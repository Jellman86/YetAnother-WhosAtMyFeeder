import { describe, expect, it } from 'vitest';
import { providerNeedsAttention } from './provider-warning';
import type { ClassifierStatus } from '../api/classifier';

const base: ClassifierStatus = { enabled: true, loaded: true, labels_count: 1, error: null };
describe('provider warning', () => {
    it('warns when an explicit accelerator falls back even without an explanation', () => {
        expect(providerNeedsAttention({ ...base, selected_provider: 'intel_gpu', active_provider: 'cpu' })).toBe(true);
    });
    it('does not mistake automatic CPU selection for a failed accelerator', () => {
        expect(providerNeedsAttention({ ...base, selected_provider: 'auto', active_provider: 'cpu' })).toBe(false);
    });
    it('does not invent a warning before a provider is known or classification is enabled', () => {
        expect(providerNeedsAttention(null)).toBe(false);
        expect(providerNeedsAttention({ ...base, selected_provider: 'intel_gpu' })).toBe(false);
        expect(providerNeedsAttention({ ...base, enabled: false, fallback_reason: 'disabled' })).toBe(false);
    });
});
