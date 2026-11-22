import { describe, expect, it } from 'vitest';
import camerasSource from './sections/CamerasSection.svelte?raw';
import integrationsSource from './sections/IntegrationsSection.svelte?raw';
import notificationsSource from './sections/NotificationsSection.svelte?raw';
import accessSource from './sections/AccessSection.svelte?raw';
import asideSource from './sections/SectionAside.svelte?raw';
import channelsSource from './NotificationChannelsSettings.svelte?raw';
import rulesSource from './NotificationSettings.svelte?raw';
import sentenceSource from './NotificationPolicySentence.svelte?raw';
import cardSource from './_primitives/SettingsCard.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';
import { SETTINGS_SECTION_PARTS, type SettingsSection } from '../../settings/settings-route';
import { settingsSearchEntry, settingsSearchInMore, settingsSearchSection } from '../../settings/settings-search-index';
import { settingsPartIsInMore } from '../../settings/settings-more';

const SECTION_SOURCES: Partial<Record<SettingsSection, string>> = {
    cameras: camerasSource,
    integrations: integrationsSource,
    notifications: notificationsSource,
    access: accessSource
};

/** The parts a section file draws, in the order it draws them. */
function partsDrawn(source: string): string[] {
    return [...new Set([...source.matchAll(/data-settings-part="([^"]+)"/g)].map((match) => match[1]))];
}

describe('the Integrations, Notifications and Access & privacy sections', () => {
    it.each(Object.entries(SECTION_SOURCES))('%s draws the parts the route gives it, in order', (section, source) => {
        expect(source).toContain(`data-settings-section="${section}"`);
        expect(partsDrawn(source)).toEqual([...SETTINGS_SECTION_PARTS[section as SettingsSection]]);
    });

    it('puts every external service on the first screen of Integrations, each with its own switch and state', () => {
        const more = integrationsSource.indexOf('<SectionMore');
        for (const part of ['birdnet', 'weather', 'networks', 'ai']) {
            const at = integrationsSource.indexOf(`data-settings-part="${part}"`);
            expect(at, part).toBeGreaterThan(-1);
            expect(at, part).toBeLessThan(more);
            expect(settingsPartIsInMore(part as 'birdnet'), part).toBe(false);
        }
        // Only where species pages get their information, which is a result of the others, is behind More options.
        expect(integrationsSource.indexOf('data-settings-part="enrichment"')).toBeGreaterThan(more);
        expect(settingsPartIsInMore('enrichment')).toBe(true);
        // A group says its state in words under its description, from one helper.
        expect(cardSource).toContain('data-settings-card-status>{status}</p>');
    });

    it('says in words where Frigate, MQTT and the feeder location are set, with a link to each', () => {
        expect(integrationsSource).toContain('data-integrations-elsewhere');
        expect(integrationsSource).toContain("href={toAppPath(settingsPartPath('connection'))}");
        expect(integrationsSource).toContain("href={toAppPath(settingsPartPath('location'))}");
        expect(integrationsSource).toContain("values: { section: settingsSectionName('cameras', $_) }");
    });

    it('keeps the feeder location on the first screen of Cameras & connection, and BirdNET-Go out of it', () => {
        expect(camerasSource.indexOf('data-settings-part="location"')).toBeLessThan(camerasSource.indexOf('<SectionMore'));
        expect(camerasSource).not.toContain('BirdnetSettings');
        expect(integrationsSource).toContain('<BirdnetSettings');
    });

    it('leaves Access & privacy with sign-in, guest access and telemetry, and no More options', () => {
        expect(accessSource).toContain('<AuthenticationSettings');
        expect(accessSource).toContain('<TelemetrySettings');
        expect(accessSource).not.toContain('<SectionMore');
        expect(accessSource).not.toContain('IntegrationSettings');
        expect(accessSource).not.toContain('LocationSettings');
    });

    it('measures BirdNET-Go in Integrations and the channels in Notifications', () => {
        expect(asideSource).toContain("cameras: ['frigate', 'mqtt'],");
        expect(asideSource).toContain("integrations: ['audio'],");
        expect(asideSource).toContain("notifications: ['notifications'],");
        expect(asideSource).toContain('access: [],');
        expect(settingsPageSource).toContain("key === 'notifications' ? 'channels' : key === 'audio' ? 'birdnet' : 'connection'");
    });
});

describe('every notification channel', () => {
    const CHANNELS = ['discord', 'pushover', 'telegram', 'email'] as const;

    /** One channel's block of the channels card, up to the next channel. */
    function channelBlock(channel: string): string {
        const start = channelsSource.indexOf(`data-notification-channel="${channel}"`);
        const next = channelsSource.indexOf('data-notification-channel="', start + 1);
        return channelsSource.slice(start, next === -1 ? undefined : next);
    }

    it.each(CHANNELS)('%s has a switch for sending the photo, bound to its own setting', (channel) => {
        const block = channelBlock(channel);
        expect(block).toContain(`checked={${channel}IncludeSnapshot}`);
        expect(block).toContain(`(${channel}IncludeSnapshot = value)`);
        expect(settingsPageSource).toContain(`notifications_${channel}_include_snapshot: ${channel}IncludeSnapshot,`);
        expect(settingsPageSource).toContain(`{ field: 'notifications_${channel}_include_snapshot', draft: ${channel}IncludeSnapshot,`);
        expect(notificationsSource).toContain(`bind:${channel}IncludeSnapshot`);
    });

    it.each(['discord', 'pushover', 'telegram'])('%s shows its photo switch as a row the search can land on', (channel) => {
        const entry = settingsSearchEntry(`setting-${channel}-include-snapshot`);
        expect(entry?.part).toBe('channels');
        expect(entry?.behind).toBe(`${channel}-channel-label`);
        expect(channelBlock(channel)).toContain(`labelId="setting-${channel}-include-snapshot"`);
    });

    it.each(CHANNELS)('%s keeps its test in the shared diagnostic dialog', (channel) => {
        expect(channelBlock(channel)).toContain('data-settings-test="notifications"');
        expect(channelsSource).toContain('<DiagnosticDialog');
    });
});

describe('custom notification rules', () => {
    it('are three switches under the sentence, and changing one makes the mode custom', () => {
        for (const id of ['setting-notify-on-insert', 'setting-notify-on-update', 'setting-notify-delay-video']) {
            expect(rulesSource).toContain(`labelId="${id}"`);
            expect(settingsSearchEntry(id)?.disclosures).toEqual(['notifications-custom-rules']);
        }
        expect(rulesSource).toContain('id={NOTIFICATION_CUSTOM_RULES_ID}');
        expect(rulesSource).toContain("notifyMode = 'custom';");
        // The switches are on the first screen, in the card that holds the sentence.
        expect(rulesSource.indexOf('id={NOTIFICATION_CUSTOM_RULES_ID}')).toBeLessThan(rulesSource.indexOf('{:else}'));
    });

    it('are what the sentence points at, by opening them', () => {
        expect(sentenceSource).toContain('data-policy-custom-rules');
        expect(sentenceSource).toContain('customRules.open = true;');
        expect(sentenceSource).toContain("settings.notifications.sentence.custom_hint");
    });
});

describe('a setting that moved is found where it is now', () => {
    it.each([
        ['setting-ebird-api-key', 'integrations'],
        ['settings-group-integrations-birdnet', 'integrations'],
        ['setting-birdnet-url', 'integrations'],
        ['settings-group-integrations-ha-weather', 'integrations'],
        ['setting-llm-enabled', 'integrations'],
        ['setting-location-mode', 'cameras'],
        ['setting-telemetry', 'access'],
        ['settings-group-auth', 'access'],
        // A guest-access setting about the location, not the feeder's location itself.
        ['setting-public-location-precision', 'access'],
        ['garden-notifications', 'notifications'],
        ['notification-channels', 'notifications']
    ] as const)('%s is in %s, on its first screen', (anchor, section) => {
        const entry = settingsSearchEntry(anchor);
        expect(entry, anchor).not.toBeNull();
        if (!entry) return;
        expect(settingsSearchSection(entry)).toBe(section);
        expect(settingsSearchInMore(entry)).toBe(false);
    });

    it('still opens More options for what stayed behind it', () => {
        for (const anchor of ['settings-group-enrichment', 'notification-cooldown-label', 'setting-frigate-external-url']) {
            const entry = settingsSearchEntry(anchor);
            expect(entry && settingsSearchInMore(entry), anchor).toBe(true);
        }
    });
});
