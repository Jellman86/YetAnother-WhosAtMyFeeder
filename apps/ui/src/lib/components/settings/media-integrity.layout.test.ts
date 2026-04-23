import { describe, expect, it } from 'vitest';
import dataSettingsSource from './DataSettings.svelte?raw';

describe('media integrity settings layout', () => {
    it('defaults the policy to mark-only with the daily scan off', () => {
        expect(dataSettingsSource).toContain("frigateMissingBehavior = $bindable<'mark_missing' | 'keep' | 'delete'>('mark_missing')");
        expect(dataSettingsSource).toContain('autoPurgeMissingClips = $bindable(false)');
        expect(dataSettingsSource).toContain('autoPurgeMissingSnapshots = $bindable(false)');
    });

    it('uses one policy selector with one daily toggle and one manual scan action', () => {
        expect(dataSettingsSource).toContain('autoMediaIntegrityScan');
        expect(dataSettingsSource).toContain('handlePurgeMissingMedia');
        expect(dataSettingsSource).toContain("$_('settings.data.purge_missing_media'");
        expect(dataSettingsSource).toContain("$_('settings.data.auto_purge_missing_media'");

        expect(dataSettingsSource).not.toContain('handlePurgeMissingClips');
        expect(dataSettingsSource).not.toContain('handlePurgeMissingSnapshots');
        expect(dataSettingsSource).not.toContain("$_('settings.data.purge_missing_clips'");
        expect(dataSettingsSource).not.toContain("$_('settings.data.purge_missing_snapshots'");
    });
});
