import { describe, expect, it } from 'vitest';
import aiSettingsSource from './AISettings.svelte?raw';
import modalSource from './AITestModal.svelte?raw';
import dialogSource from '../DiagnosticDialog.svelte?raw';

describe('AI settings diagnostic modal', () => {
    it('opens a focus-managed dialog with determinate stage progress', () => {
        expect(aiSettingsSource).toContain('testModalOpen = true');
        expect(aiSettingsSource).toContain('<AITestModal');
        // The reusable DiagnosticDialog owns the accessible modal chrome.
        expect(modalSource).toContain('<DiagnosticDialog');
        expect(dialogSource).toContain('role="dialog"');
        expect(dialogSource).toContain('aria-modal="true"');
        expect(dialogSource).toContain('role="progressbar"');
        expect(dialogSource).toContain('trapFocus');
        // Overlays must escape nested stacking contexts to cover the whole page.
        expect(dialogSource).toContain('use:portal');
    });

    it('shows every backend diagnostic stage and offers an explicit retry', () => {
        for (const stage of ['configuration', 'provider', 'vision', 'multi_frame', 'response']) {
            expect(modalSource).toContain(`id: '${stage}'`);
        }
        expect(modalSource).toContain('retry_after_seconds');
        expect(modalSource).toContain('onRetry');
        expect(modalSource).toContain('test_probe_note');
    });
});
