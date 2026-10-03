import { describe, expect, it } from 'vitest';
import statusSource from './ConnectionStatus.svelte?raw';
import sidebarSource from './Sidebar.svelte?raw';
import avatarStoreSource from '../stores/avatar.svelte.ts?raw';
import authSettingsSource from './settings/AuthenticationSettings.svelte?raw';
import en from '../i18n/locales/en.json';

describe('the sidebar status tiles', () => {
    it('shows three icon tiles with one-word names instead of three sentences', () => {
        expect(statusSource).toContain('grid grid-cols-3');
        expect(statusSource).toContain('data-status-tiles');
        expect(en.status.tile_live).toBe('Live');
        expect(en.status.tile_audio).toBe('Audio');
        expect(en.status.tile_alerts).toBe('Alerts');
    });

    it('never says on or off by colour alone', () => {
        // Off is a slash through the icon as well as a muted colour.
        expect(statusSource).toContain('{#if !tile.on}<path d="M4 4l16 16" />{/if}');
        // The full sentence is the tooltip and the screen-reader text.
        expect(statusSource).toContain('title={`${tile.name}: ${tile.state}`}');
        expect(statusSource).toContain('<span class="sr-only">{tile.name}: {tile.state}</span>');
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
