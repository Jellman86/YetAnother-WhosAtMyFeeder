import { describe, expect, it } from 'vitest';
import statusSource from './ConnectionStatus.svelte?raw';
import sidebarSource from './Sidebar.svelte?raw';
import avatarStoreSource from '../stores/avatar.svelte.ts?raw';
import authSettingsSource from './settings/AuthenticationSettings.svelte?raw';
import enSettings from '../i18n/locales/en/settings.json';
import enStatus from '../i18n/locales/en/status.json';

const en = { settings: enSettings, status: enStatus };

describe('the sidebar status list', () => {
    it('is a list of rows that say each state in words', () => {
        expect(statusSource).toContain('data-status-list');
        expect(statusSource).toContain('data-status-label');
        expect(statusSource).toContain('data-status-state');
        expect(en.status.row_feed).toBe('Frigate events');
        expect(en.status.row_audio).toBe('Audio');
        expect(en.status.row_alerts).toBe('Alerts');
        expect(en.status.state_live).toBe('Live');
        expect(en.status.state_waiting).toBe('Waiting for events');
        expect(en.status.state_not_connected).toBe('Not connected');
        expect(en.status.state_listening).toBe('Listening');
        expect(en.status.state_off).toBe('Off');
    });

    it('never says a state by colour alone', () => {
        // Working, needs a person, and off each have their own dot shape as well as a colour.
        expect(statusSource).toMatch(/ok: 'h-1\.5 w-1\.5 rounded-full bg-status-ok-line'/);
        expect(statusSource).toMatch(/attention: 'h-2 w-2 rotate-45 bg-status-attention-line'/);
        expect(statusSource).toMatch(/neutral: 'h-2 w-2 rounded-full border-2 border-status-neutral-line'/);
        // The full sentence is the tooltip; the icon rail names each icon with the same words.
        expect(statusSource).toContain('title={say(row.detail)}');
        expect(statusSource).toContain('<span class="sr-only">{say(row.label)}: {say(row.state)}</span>');
    });

    it('is one live region whose rows are read whole', () => {
        expect(statusSource.match(/role="status"/g) ?? []).toHaveLength(1);
        expect(statusSource).not.toContain('animate-');
        expect(statusSource.match(/aria-atomic="true"/g) ?? []).toHaveLength(2);
    });
});

describe('the profile picture', () => {
    it('shows the owner picture in the account card, the initial without one', () => {
        expect(sidebarSource).toContain('{#if avatarStore.url}');
        expect(sidebarSource).toContain('data-sidebar-avatar');
        expect(sidebarSource).toContain('{accountInitial}');
        // A guest or signed-out viewer never fetches it.
        expect(sidebarSource).toContain('avatarStore.sync(authStore.isAuthenticated ? authStore.avatarVersion : null);');
    });

    it('is fetched with the owner credentials and its old object URL released', () => {
        expect(avatarStoreSource).toContain('fetchAvatar()');
        expect(avatarStoreSource).toContain('URL.revokeObjectURL(this.url)');
        // A slow earlier fetch never overwrites a newer picture.
        expect(avatarStoreSource).toContain('if (generation !== this.generation) return;');
    });

    it('saves when chosen, so its buttons say so, and checks the size first', () => {
        expect(authSettingsSource).toContain('data-settings-avatar');
        expect(authSettingsSource).toContain('if (file.size > AVATAR_MAX_BYTES)');
        expect(authSettingsSource).toContain("settings.auth.avatar_upload");
        expect(authSettingsSource).toContain("settings.auth.avatar_remove");
        expect(en.settings.auth.avatar_desc).toContain('nothing else from the file is kept');
    });
});
