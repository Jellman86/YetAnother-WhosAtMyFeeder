import { describe, expect, it } from 'vitest';
import {
    enabledChannelNames,
    formatChannelList,
    policyChannels,
    presetSentenceKey,
    speciesSummaryKey,
    type PolicyChannel,
} from './notification-policy';

const channel = (
    id: PolicyChannel['id'],
    label: string,
    enabled: boolean
): PolicyChannel => ({ id, label, enabled, configured: true });

describe('notification policy sentence helpers', () => {
    it('maps every notify mode to its sentence key', () => {
        expect(presetSentenceKey('standard')).toBe('settings.notifications.sentence.what_standard');
        expect(presetSentenceKey('final')).toBe('settings.notifications.sentence.what_final');
        expect(presetSentenceKey('realtime')).toBe('settings.notifications.sentence.what_realtime');
        expect(presetSentenceKey('silent')).toBe('settings.notifications.sentence.what_silent');
        expect(presetSentenceKey('custom')).toBe('settings.notifications.sentence.what_custom');
    });

    it('summarises the species filter by mode and list size', () => {
        expect(speciesSummaryKey('none', 0)).toBe('settings.notifications.sentence.species_any');
        expect(speciesSummaryKey('blacklist', 3)).toBe(
            'settings.notifications.sentence.species_all_but'
        );
        expect(speciesSummaryKey('whitelist', 2)).toBe(
            'settings.notifications.sentence.species_only'
        );
    });

    it('treats an empty filter list as no filter, whatever the mode says', () => {
        expect(speciesSummaryKey('blacklist', 0)).toBe('settings.notifications.sentence.species_any');
        expect(speciesSummaryKey('whitelist', 0)).toBe('settings.notifications.sentence.species_any');
    });

    it('lists only enabled channels, in order', () => {
        const names = enabledChannelNames([
            channel('discord', 'Discord', true),
            channel('pushover', 'Pushover', false),
            channel('email', 'Email', true),
        ]);
        expect(names).toEqual(['Discord', 'Email']);
    });

    it('joins channel names with the locale list format', () => {
        expect(formatChannelList(['Discord'], 'en')).toBe('Discord');
        expect(formatChannelList(['Discord', 'Email'], 'en')).toBe('Discord and Email');
        expect(formatChannelList(['Discord', 'Telegram', 'Email'], 'en')).toBe(
            'Discord, Telegram, and Email'
        );
        expect(formatChannelList([], 'en')).toBe('');
    });

    it('falls back to a comma join when the locale is unusable', () => {
        expect(formatChannelList(['Discord', 'Email'], 'not-a-locale-!!')).toBe('Discord, Email');
    });
});

describe('policyChannels', () => {
    const draft = {
        discord: { enabled: true, webhook: '', webhookSaved: true },
        pushover: { enabled: false, user: 'u', userSaved: false, token: '', tokenSaved: false },
        telegram: { enabled: false, token: '', tokenSaved: true, chatId: '', chatIdSaved: true },
        email: { enabled: true, useOAuth: true, connectedEmail: '', smtpHost: 'smtp', toEmail: 'a@b' }
    };

    it('names every channel and says whether it can send, saved secrets included', () => {
        const channels = policyChannels(draft, (id) => id.toUpperCase());
        expect(channels.map((channel) => [channel.id, channel.label, channel.enabled, channel.configured])).toEqual([
            ['discord', 'DISCORD', true, true],
            ['pushover', 'PUSHOVER', false, false],
            ['telegram', 'TELEGRAM', false, true],
            // Signed-in email needs the connected address, not the SMTP fields.
            ['email', 'EMAIL', true, false]
        ]);
    });
});
