import { describe, expect, it } from 'vitest';
import aiSettingsSource from './AISettings.svelte?raw';
import modalSource from './AITestModal.svelte?raw';

describe('AI settings diagnostic modal', () => {
    it('opens a focus-managed dialog with determinate stage progress', () => {
        expect(aiSettingsSource).toContain('testModalOpen = true');
        expect(aiSettingsSource).toContain('<AITestModal');
        expect(modalSource).toContain('role="dialog"');
        expect(modalSource).toContain('aria-modal="true"');
        expect(modalSource).toContain('role="progressbar"');
        expect(modalSource).toContain('trapFocus');
    });

    it('shows every backend diagnostic stage and offers an explicit retry', () => {
        for (const stage of ['configuration', 'provider', 'vision', 'multi_frame', 'response']) {
            expect(modalSource).toContain(`id: '${stage}'`);
        }
        expect(modalSource).toContain('result.retry_after_seconds');
        expect(modalSource).toContain('onRetry');
        expect(modalSource).toContain('test_probe_note');
    });
});
