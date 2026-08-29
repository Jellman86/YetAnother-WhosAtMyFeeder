import { describe, expect, it } from 'vitest';
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
        expect(sentenceSource).toContain('onAudioOnlyChange(event.currentTarget.checked)');
        expect(sentenceSource).toContain('policy-video-fallback');
        expect(settingsSource).toContain("$_('settings.notifications.cooldown')");
    });

    it('names every destination in the sentence and lets several be chosen at once', () => {
        expect(sentenceSource).toContain('formatChannelList');
        expect(sentenceSource).toContain('enabledChannelNames');
        expect(sentenceSource).toContain('type="checkbox"');
        expect(sentenceSource).toContain('onChannelToggle(channel.id, event.currentTarget.checked)');
        expect(settingsSource).toContain('function togglePolicyChannel');
        for (const id of ['discord', 'pushover', 'telegram', 'email']) {
            expect(settingsSource).toContain(`id: '${id}'`);
        }
    });

    it('keeps the interactive slots accessible', () => {
        expect(sentenceSource).toContain('aria-haspopup="dialog"');
        expect(sentenceSource).toContain('aria-expanded={openSlot ===');
        expect(sentenceSource).toContain("event.key === 'Escape'");
        expect(sentenceSource).toContain('role="dialog"');
        expect(sentenceSource).toContain('removeEventListener');
    });

    it('is honest about unconfigured destinations instead of hiding them', () => {
        expect(sentenceSource).toContain('channel_needs_setup');
        expect(sentenceSource).toContain('channels_none');
    });

    it('links the species slot to the real filter editor rather than duplicating it', () => {
        expect(sentenceSource).toContain('speciesSectionId');
        expect(sentenceSource).toContain('scrollIntoView');
        expect(settingsSource).toContain('id={speciesFilterSectionId}');
    });
});
