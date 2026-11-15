import { describe, expect, it } from 'vitest';
import policySource from '../../settings/notification-policy.ts?raw';
import sentenceSource from './NotificationPolicySentence.svelte?raw';
import settingsSource from './NotificationSettings.svelte?raw';

describe('Notification policy sentence', () => {
    it('replaces the preset grid and the standalone confidence slider', () => {
        expect(settingsSource).toContain('<NotificationPolicySentence');
        expect(settingsSource).not.toContain("setMode('final')");
        expect(settingsSource).not.toContain('notify-confidence-slider');
    });

    it('absorbs the advanced delivery toggles and the audio-only panel', () => {
        expect(settingsSource).not.toContain('notifications-delivery-advanced');
        expect(settingsSource).not.toContain('notify-insert-label');
        expect(settingsSource).not.toContain('audio-only-label');
        expect(sentenceSource).toContain('confidence_chip_audio');
        // Audio-only is an on/off setting, so it is the shared switch.
        expect(sentenceSource).toContain('onchange={onAudioOnlyChange}');
        expect(sentenceSource).toContain('<SettingsToggle');
        expect(sentenceSource).toContain('policy-video-fallback');
        expect(settingsSource).toContain("$_('settings.notifications.cooldown')");
    });

    it('names every destination in the sentence and links to the channels, the one place each is switched on', () => {
        expect(sentenceSource).toContain('formatChannelList');
        expect(sentenceSource).toContain('enabledChannelNames');
        expect(sentenceSource).not.toContain('type="checkbox"');
        expect(sentenceSource).not.toContain('onChannelToggle');
        expect(sentenceSource).toContain('jumpTo(channelsSectionId)');
        expect(settingsSource).toContain('id={channelsSectionId}');
        expect(policySource).toContain("id: 'discord'");
        for (const id of ['pushover', 'telegram', 'email']) {
            expect(policySource).toContain(`id: '${id}'`);
        }
    });

    it('keeps the interactive slots accessible', () => {
        expect(sentenceSource).toContain('aria-haspopup="dialog"');
        expect(sentenceSource).toContain('aria-expanded={openSlot ===');
        expect(sentenceSource).toContain("event.key === 'Escape'");
        expect(sentenceSource).toContain('role="dialog"');
        expect(sentenceSource).toContain('removeEventListener');
    });

    it('says in words when no channel is on yet', () => {
        expect(sentenceSource).toContain('channels_none');
    });

    it('links the species slot to the real filter editor rather than duplicating it', () => {
        expect(sentenceSource).toContain('jumpTo(speciesSectionId)');
        expect(sentenceSource).toContain('data-policy-species-link');
        expect(sentenceSource).toContain('scrollIntoView');
        expect(settingsSource).toContain('id={speciesFilterSectionId}');
    });
});
