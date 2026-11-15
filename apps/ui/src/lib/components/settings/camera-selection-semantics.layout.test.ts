import { describe, expect, it } from 'vitest';

import connectionSettingsSource from './ConnectionSettings.svelte?raw';
import rowSource from './CameraWatchRow.svelte?raw';

describe('Connection camera selection semantics', () => {
    it('keeps the watch choice, the role and preview as separate native controls on one compact row', () => {
        expect(rowSource).not.toContain('role="button"');
        expect(rowSource).not.toContain('role="presentation"');
        // One single-choice control per camera, named by its combinations (layout-patterns §6).
        expect(rowSource).toContain('data-camera-watch-select');
        expect(rowSource.match(/<select\b/g)).toHaveLength(2);
        expect(rowSource).toContain('aria-expanded={previewOpen}');
        expect(connectionSettingsSource).toContain('previewOpen={previewVisible && previewCamera === row.camera}');
        expect(rowSource).toContain('select-base min-h-11');
        // A row, not a card inside the card.
        expect(rowSource).not.toMatch(/<li[^>]*rounded-xl border/);
    });

    it('names each camera in its controls', () => {
        // WCAG 2.5.3: the visible camera name is in the accessible name of every group and
        // control on its row, so "Birds" on one row is distinguishable from the next.
        expect(rowSource).toContain("$_('settings.cameras.watch_for', { default: '{camera}: watch for', values: { camera } })");
        expect(rowSource).toContain("$_('settings.cameras.role_group', { default: '{camera}: bird role', values: { camera } })");
        expect(rowSource).toContain("$_('settings.beta.garden_motion_toggle', { default: 'Collect motion review photos on {camera}', values: { camera } })");
        expect(rowSource).toContain('<span class="sr-only"> {camera}</span>');
    });

    it('says why a choice is unavailable, next to the choice', () => {
        expect(rowSource).toContain('disabled={!!row.blocked[option.value]}');
        expect(rowSource).toContain('data-camera-watch-reason');
        expect(rowSource).toContain("aria-describedby={blockReasons.length > 0 ? `${uid}-reason` : undefined}");
    });

    it('shows the chosen option as the select value, never by colour', () => {
        expect(rowSource).toContain('value={row.mode}');
        expect(rowSource).toContain("value={row.role ?? 'feeder'}");
    });

    it('keeps a configured camera Frigate no longer lists, flagged in words', () => {
        expect(rowSource).toContain("row.presence === 'missing'");
        expect(rowSource).toContain('data-camera-missing');
        expect(rowSource).toContain('attention-dot');
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
