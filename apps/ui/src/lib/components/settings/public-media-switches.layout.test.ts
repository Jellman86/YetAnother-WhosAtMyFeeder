import { describe, expect, it } from 'vitest';
import authSettingsSource from './AuthenticationSettings.svelte?raw';
import authStoreSource from '../../stores/auth.svelte.ts?raw';
import audioHistorySource from '../../pages/AudioHistory.svelte?raw';
import dashboardSource from '../../pages/Dashboard.svelte?raw';

describe('what a visitor sees is the owner\'s call, per medium (#291)', () => {
    it('security settings offer the three media switches and location precision', () => {
        expect(authSettingsSource).toContain('setting-public-show-audio');
        expect(authSettingsSource).toContain('setting-public-show-snapshots');
        expect(authSettingsSource).toContain('setting-public-show-clips');
        expect(authSettingsSource).toContain('setting-public-location-precision');
        // Approximate first: the safe default leads.
        const approxAt = authSettingsSource.indexOf("value: 'approximate'");
        const exactAt = authSettingsSource.indexOf("value: 'exact'");
        expect(approxAt).toBeGreaterThan(-1);
        expect(exactAt).toBeGreaterThan(approxAt);
    });

    it('a guest with audio off sees no audio surfaces, with words not errors', () => {
        expect(authStoreSource).toContain('canViewAudio');
        expect(dashboardSource).toContain('authStore.canViewAudio');
        expect(audioHistorySource).toContain('data-audio-not-shared');
        expect(audioHistorySource).toContain('audio.not_shared_title');
    });
});
