import { describe, expect, it } from 'vitest';
import connectionSettingsSource from './ConnectionSettings.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';
import settingsApiSource from '../../api/settings.ts?raw';
import systemApiSource from '../../api/system.ts?raw';

describe('full-visit clip settings gate wiring', () => {
    it('threads recording clip settings and capability through the connection settings flow', () => {
        expect(settingsApiSource).toContain('recording_clip_enabled');
        expect(settingsApiSource).toContain('recording_clip_before_seconds');
        expect(settingsApiSource).toContain('recording_clip_after_seconds');

        expect(systemApiSource).toContain('fetchRecordingClipCapability');
        expect(systemApiSource).toContain('RecordingClipCapability');

        expect(settingsPageSource).toContain('recordingClipEnabled');
        expect(settingsPageSource).toContain('recordingClipBeforeSeconds');
        expect(settingsPageSource).toContain('recordingClipAfterSeconds');
        expect(settingsPageSource).toContain('recordingClipCapability');
        expect(settingsPageSource).toContain('fetchRecordingClipCapability');
        expect(settingsPageSource).toContain('bind:recordingClipEnabled');
        expect(settingsPageSource).toContain('bind:recordingClipBeforeSeconds');
        expect(settingsPageSource).toContain('bind:recordingClipAfterSeconds');

        expect(connectionSettingsSource).toContain('recordingClipEnabled = $bindable(false)');
        expect(connectionSettingsSource).toContain('recordingClipBeforeSeconds = $bindable(30)');
        expect(connectionSettingsSource).toContain('recordingClipAfterSeconds = $bindable(90)');
        expect(connectionSettingsSource).toContain('recordingClipCapability');
        expect(connectionSettingsSource).toContain('canToggleRecordingClips');
        expect(connectionSettingsSource).toContain('disabled={!canToggleRecordingClips}');
    });
});
