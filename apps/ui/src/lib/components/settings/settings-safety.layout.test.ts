import { describe, expect, it } from 'vitest';
import dataSource from './DataSettings.svelte?raw';
import maintenanceSource from './MaintenanceSettings.svelte?raw';
import dangerSource from './DangerZoneSettings.svelte?raw';
import storageSectionSource from './sections/StorageSection.svelte?raw';
import notificationRulesSource from './NotificationSettings.svelte?raw';
import notificationChannelsSource from './NotificationChannelsSettings.svelte?raw';

// Alerts' rules and its channels are two components; these checks read them as one.
const notificationSource = `${notificationRulesSource}\n${notificationChannelsSource}`;
import settingsPageSource from '../../pages/Settings.svelte?raw';
import sharingSource from './sections/SharingSection.svelte?raw';
import enSettings from '../../i18n/locales/en/settings.json';

const en = { settings: enSettings };

describe('history retention', () => {
    it('states the saved history in one sentence, in words, instead of stat tiles', () => {
        expect(dataSource).toContain('data-history-summary');
        expect(dataSource).toContain("settings.data.history_due");
        expect(dataSource).not.toContain("'∞'");
        expect(dataSource).not.toContain('pending_gc');
        expect(dataSource).not.toContain('grid grid-cols-2 md:grid-cols-4');
    });

    it('warns under the picker, and links the warning to it, when a choice deletes history', () => {
        expect(dataSource).toContain("ariaDescribedBy={retentionNote ? 'retention-deletion-note' : undefined}");
        expect(dataSource).toContain('id="retention-deletion-note"');
        expect(settingsPageSource).toContain('{retentionNote}');
    });

    it('asks before saving a retention that deletes history', () => {
        const save = settingsPageSource.slice(settingsPageSource.indexOf('async function saveSettings'));
        expect(save.indexOf('confirmRetentionChange()')).toBeGreaterThan(-1);
        expect(save.indexOf('confirmRetentionChange()')).toBeLessThan(save.indexOf('await updateSettings('));
        expect(en.settings.data.retention_confirm_title).toBe('Delete older history?');
    });

    it('says why Purge Old Records is unavailable', () => {
        expect(dataSource).toContain("aria-describedby={purgeDisabledReason ? 'purge-disabled-reason' : undefined}");
        expect(en.settings.data.purge_disabled_forever).toBe('Nothing to purge: history is kept forever.');
        expect(en.settings.data.purge_disabled_none).toBe('No captures are older than {days} days.');
    });
});

describe('the Danger Zone', () => {
    it('gives each action its own block, ordered by reach, with its consequence beside its button', () => {
        const order = ['feedback', 'favorites', 'reset'].map((action) => dangerSource.indexOf(`data-danger-action="${action}"`));
        expect(order.every((at) => at > -1)).toBe(true);
        expect([...order].sort((a, b) => a - b)).toEqual(order);
        for (const action of ['feedback', 'favorites', 'reset']) {
            expect(dangerSource).toContain(`aria-describedby="danger-${action}-consequence"`);
        }
        // Deleting data is last in Storage & upkeep, after More options and outside it.
        expect(storageSectionSource.indexOf('<DangerZoneSettings')).toBeGreaterThan(storageSectionSource.indexOf('</SectionMore>'));
    });

    it('uses the kit danger buttons, solid only for the reset, and red only where something is deleted', () => {
        expect(dangerSource).not.toContain('buttonAmberClass');
        expect(dangerSource).toContain("const buttonDangerSolidClass = 'btn btn-danger-solid");
        const reset = dangerSource.slice(dangerSource.indexOf('data-danger-action="reset"'));
        expect(reset).toContain('{buttonDangerSolidClass}');
        expect(dangerSource.match(/\{buttonDangerSolidClass\}/g)).toHaveLength(1);
        // Repairs and the integrity scan change nothing for good, so they are not red; the scan
        // turns red only while the chosen policy deletes local data.
        expect(maintenanceSource).not.toMatch(/buttonDanger(Outline|Solid)Class\}/);
        expect(dataSource).toContain("class={frigateMissingBehavior === 'delete' ? buttonDangerOutlineClass : buttonNeutralClass}");
    });

    it('asks in a calm sentence that states the effect and the count', () => {
        for (const key of ['confirm', 'clear_feedback_confirm', 'reset_desc']) {
            const value = (en.settings.danger as Record<string, string>)[key];
            expect(value, key).not.toMatch(/DANGER|\bALL\b|Are you sure/);
        }
        expect(en.settings.danger.confirm).toContain('{count');
        // The disclosure says what it holds once; its description adds something new.
        expect(en.settings.danger.subtitle).not.toBe('Destructive actions');
    });
});

describe('notification test buttons', () => {
    it('use the kit secondary button with a 44px target, not hand-rolled colours', () => {
        expect(notificationSource).not.toMatch(/bg-(?:indigo|blue|sky)-500 hover:bg-/);
        // A test is a secondary action; a section holds at most one primary.
        expect(notificationSource.match(/class="btn btn-secondary min-h-11 px-4"/g)?.length).toBeGreaterThanOrEqual(4);
        expect(notificationSource).not.toContain('btn-primary');
    });

    it('state why each test is unavailable', () => {
        for (const channel of ['discord', 'pushover', 'telegram', 'email']) {
            expect(notificationSource).toContain(`aria-describedby={${channel}Ready ? undefined : '${channel}-test-reason'}`);
            expect(notificationSource).toContain(`id="${channel}-test-reason"`);
        }
        expect(en.settings.discord.test_needs).toBe('Enter the webhook URL to send a test.');
    });
});

describe('the HTTPS warning', () => {
    it('is translated and takes the attention tone in every mode', () => {
        const band = sharingSource.slice(sharingSource.indexOf('{#if authStore.httpsWarning}'));
        const markup = band.slice(0, band.indexOf('{/if}'));
        expect(markup).not.toContain('Security Warning:');
        expect(markup).toContain("settings.security.https_warning'");
        expect(markup).toContain('bg-status-attention-soft');
        expect(markup).not.toContain('dark:');
        expect(en.settings.security.https_warning).toContain('Serve YA-WAMF over HTTPS, for example behind your reverse proxy.');
    });
});

describe('the Show camera names switch', () => {
    it('describes what guests see when it is on', () => {
        expect(en.settings.public_access.show_camera_names_desc).toBe('Guests see each camera’s name. Off shows a generic label.');
    });
});
