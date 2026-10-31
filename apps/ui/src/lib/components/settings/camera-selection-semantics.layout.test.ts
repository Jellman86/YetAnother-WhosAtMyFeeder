import { describe, expect, it } from 'vitest';

import connectionSettingsSource from './ConnectionSettings.svelte?raw';
import rowSource from './CameraWatchRow.svelte?raw';

describe('Connection camera selection semantics', () => {
    it('keeps the watch choice and preview as separate native controls', () => {
        expect(rowSource).not.toContain('role="button"');
        expect(rowSource).not.toContain('role="presentation"');
        expect(rowSource).toContain('role="radiogroup"');
        expect(rowSource).toContain('type="radio"');
        expect(rowSource).toContain('aria-expanded={previewOpen}');
        expect(connectionSettingsSource).toContain('previewOpen={previewVisible && previewCamera === row.camera}');
        expect(rowSource).toContain('min-h-11');
        expect(rowSource).toContain('h-11 w-11');
    });

    it('names each camera in its controls', () => {
        // WCAG 2.5.3: the visible camera name is in the accessible name of every group and
        // control on its row, so "Birds" on one row is distinguishable from the next.
        expect(rowSource).toContain("$_('settings.cameras.watch_for', { default: '{camera}: watch for', values: { camera } })");
        expect(rowSource).toContain("$_('settings.cameras.role_group', { default: '{camera}: bird role', values: { camera } })");
        expect(rowSource).toContain("$_('settings.beta.garden_motion_toggle', { default: 'Collect motion review photos on {camera}', values: { camera } })");
        expect(rowSource).toContain("$_('settings.cameras.preview', { default: 'Preview {camera}', values: { camera } })");
    });

    it('says why a choice is unavailable, next to the choice', () => {
        expect(rowSource).toContain('disabled={blocked}');
        expect(rowSource).toContain('data-camera-watch-reason');
        expect(rowSource).toContain("aria-describedby={blockReasons.length > 0 ? `${uid}-reason` : undefined}");
    });

    it('marks the chosen option by shape and weight as well as colour', () => {
        expect(rowSource).toContain('{#if checked}');
        expect(rowSource).toContain('line-through');
    });

    it('keeps a configured camera Frigate no longer lists, flagged in words', () => {
        expect(rowSource).toContain("row.presence === 'missing'");
        expect(rowSource).toContain('data-camera-missing');
        expect(rowSource).toContain('bg-attention-500');
    });

    it('says why Preview is unavailable without a Frigate URL', () => {
        expect(connectionSettingsSource).toContain("previewUnavailableId={frigateUrl ? undefined : 'camera-preview-needs-url'}");
        expect(connectionSettingsSource).toContain('id="camera-preview-needs-url"');
        expect(rowSource).toContain('aria-describedby={previewUnavailableId}');
    });

    it('announces preview state and describes the preview image', () => {
        expect(connectionSettingsSource).toContain('<div role="status"');
        expect(connectionSettingsSource).toContain('<div role="alert"');
        expect(connectionSettingsSource).toContain("alt={$_('settings.cameras.preview_label'");
        expect(connectionSettingsSource).not.toContain('alt="" src={previewBlobUrl}');
    });
});
