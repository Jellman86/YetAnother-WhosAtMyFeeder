import { describe, expect, it } from 'vitest';
import dataSource from './DataSettings.svelte?raw';
import notificationSource from './NotificationSettings.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';
import enSettings from '../../i18n/locales/en/settings.json';

const en = { settings: enSettings };

describe('history retention', () => {
    it('shows the saved policy in the stat tiles, in plain words', () => {
        expect(dataSource).toContain("val: savedRetentionDays === 0 ? '∞'");
        expect(dataSource).toContain("settings.data.due_for_deletion");
        expect(dataSource).not.toContain('pending_gc');
        expect(en.settings.data.due_for_deletion).toBe('Due for deletion');
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
        expect(en.settings.data.purge_disabled_none).toBe('No detections are older than {days} days.');
    });
});

describe('the Danger Zone', () => {
    it('gives each action its own block, ordered by reach, with its consequence beside its button', () => {
        const order = ['feedback', 'favorites', 'reset'].map((action) => dataSource.indexOf(`data-danger-action="${action}"`));
        expect(order.every((at) => at > -1)).toBe(true);
        expect([...order].sort((a, b) => a - b)).toEqual(order);
        for (const action of ['feedback', 'favorites', 'reset']) {
            expect(dataSource).toContain(`aria-describedby="danger-${action}-consequence"`);
        }
    });

    it('uses the kit danger buttons, solid only for the reset', () => {
        expect(dataSource).not.toContain('buttonAmberClass');
        expect(dataSource).toContain("const buttonDangerSolidClass = 'btn btn-danger-solid");
        const reset = dataSource.slice(dataSource.indexOf('data-danger-action="reset"'));
        expect(reset).toContain('{buttonDangerSolidClass}');
        expect(dataSource.match(/\{buttonDangerSolidClass\}/g)).toHaveLength(1);
    });
});

describe('notification test buttons', () => {
    it('use the kit primary button with a 44px target, not hand-rolled colours', () => {
        expect(notificationSource).not.toMatch(/bg-(?:indigo|blue|sky)-500 hover:bg-/);
        expect(notificationSource.match(/class="btn btn-primary min-h-11 w-full px-4 py-3"/g)).toHaveLength(4);
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
    it('is translated and has a dark style', () => {
        const band = settingsPageSource.slice(settingsPageSource.indexOf('{#if authStore.httpsWarning}'));
        const markup = band.slice(0, band.indexOf('{/if}'));
        expect(markup).not.toContain('Security Warning:');
        expect(markup).toContain("settings.security.https_warning'");
        expect(markup).toContain('dark:bg-amber-950/30');
        expect(en.settings.security.https_warning).toContain('Serve YA-WAMF over HTTPS, for example behind your reverse proxy.');
    });
});

describe('the Show camera names switch', () => {
    it('describes what guests see when it is on', () => {
        expect(en.settings.public_access.show_camera_names_desc).toBe('Guests see each camera’s name. Off shows a generic label.');
    });
});
