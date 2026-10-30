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

    it('names each camera in its buttons, and keeps the toggle name steady as it is pressed', () => {
        // WCAG 2.5.3: the visible camera name is in the accessible name. A toggle with
        // aria-pressed keeps one name; "pressed" carries the state.
        expect(connectionSettingsSource).toContain("aria-label={$_('settings.cameras.select', { default: 'Watch {camera} for birds', values: { camera } })}");
        expect(connectionSettingsSource).not.toContain('settings.cameras.deselect');
        expect(connectionSettingsSource).toContain("$_('settings.cameras.preview', { default: 'Preview {camera}', values: { camera } })");
    });

    it('says why Preview is unavailable without a Frigate URL', () => {
        expect(connectionSettingsSource).toContain("aria-describedby={frigateUrl ? undefined : 'camera-preview-needs-url'}");
        expect(connectionSettingsSource).toContain('id="camera-preview-needs-url"');
    });

    it('announces preview state and describes the preview image', () => {
        expect(connectionSettingsSource).toContain('<div role="status"');
        expect(connectionSettingsSource).toContain('<div role="alert"');
        expect(connectionSettingsSource).toContain("alt={$_('settings.cameras.preview_label'");
        expect(connectionSettingsSource).not.toContain('alt="" src={previewBlobUrl}');
    });
});
