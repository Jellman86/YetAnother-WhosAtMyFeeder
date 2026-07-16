import { describe, expect, it } from 'vitest';

import connectionSettingsSource from './ConnectionSettings.svelte?raw';

describe('Connection camera selection semantics', () => {
    it('keeps selection and preview as separate native controls', () => {
        expect(connectionSettingsSource).not.toContain('role="button"');
        expect(connectionSettingsSource).not.toContain('role="presentation"');
        expect(connectionSettingsSource).toContain('aria-pressed={selected}');
        expect(connectionSettingsSource).toContain('aria-expanded={previewVisible && previewCamera === camera}');
        expect(connectionSettingsSource).toContain('min-h-11');
        expect(connectionSettingsSource).toContain('h-11 w-11');
    });

    it('announces preview state and describes the preview image', () => {
        expect(connectionSettingsSource).toContain('<div role="status"');
        expect(connectionSettingsSource).toContain('<div role="alert"');
        expect(connectionSettingsSource).toContain("alt={$_('settings.cameras.preview_label'");
        expect(connectionSettingsSource).not.toContain('alt="" src={previewBlobUrl}');
    });
});
