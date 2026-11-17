import { describe, expect, it } from 'vitest';
import {
    canonicalSettingsPath,
    SETTINGS_PART_ORDER,
    SETTINGS_SECTION_ORDER,
    SETTINGS_SECTION_PARTS,
    settingsPartFromAnchor,
    settingsPartPath,
    settingsSectionFromRoute,
    settingsSectionOfPart,
    settingsSectionPath
} from './settings-route';

describe('the six Settings sections', () => {
    it('are organised by the task an owner comes to do, in that order', () => {
        expect(SETTINGS_SECTION_ORDER).toEqual(['cameras', 'identification', 'alerts', 'sharing', 'storage', 'display']);
    });

    it('hold every former tab exactly once, as a part, and no status pages', () => {
        expect(SETTINGS_SECTION_PARTS).toEqual({
            cameras: ['connection'],
            identification: ['detection', 'models', 'beta'],
            alerts: ['notifications'],
            sharing: ['security', 'integrations', 'ai'],
            storage: ['data', 'maintenance'],
            display: ['appearance', 'accessibility']
        });
        expect(new Set(SETTINGS_PART_ORDER).size).toBe(12);
        // Health is a page of its own, and Debug's two settings moved into Models.
        expect(SETTINGS_PART_ORDER).not.toContain('health');
        expect(SETTINGS_PART_ORDER).not.toContain('debug');
    });
});

describe('settingsSectionFromRoute', () => {
    it.each([
        [undefined, 'cameras'],
        ['', 'cameras'],
        ['/settings', 'cameras'],
        ['/settings/', 'cameras'],
        ['/settings/alerts', 'alerts'],
        ['/settings/alerts/', 'alerts'],
        ['/settings/identification#models', 'identification'],
        ['/settings/storage?x=1', 'storage'],
        ['/settings/data/retention', 'storage'],
        ['/settings/not-a-section', 'cameras'],
        ['/events', 'cameras']
    ] as const)('shows %s as the %s section', (route, section) => {
        expect(settingsSectionFromRoute(route)).toBe(section);
    });
});

describe('canonicalSettingsPath', () => {
    it.each([
        ['/settings', '', '/settings/cameras'],
        ['/settings/', '', '/settings/cameras'],
        ['/settings', 'alerts', '/settings/alerts'],
        ['/settings', 'not-a-section', '/settings/cameras'],
        ['/settings/not-a-section', '', '/settings/cameras'],
        ['/settings/sharing/', '', '/settings/sharing']
    ])('rewrites the loose address %s#%s to %s', (pathname, hash, canonical) => {
        expect(canonicalSettingsPath(pathname, hash)).toBe(canonical);
    });

    it.each([
        ['/settings/connection', '/settings/cameras#connection'],
        ['/settings/detection', '/settings/identification#detection'],
        ['/settings/models', '/settings/identification#models'],
        ['/settings/beta', '/settings/identification#beta'],
        ['/settings/notifications/', '/settings/alerts#notifications'],
        ['/settings/integrations', '/settings/sharing#integrations'],
        ['/settings/ai/', '/settings/sharing#ai'],
        ['/settings/security', '/settings/sharing#security'],
        ['/settings/data', '/settings/storage#data'],
        ['/settings/maintenance', '/settings/storage#maintenance'],
        ['/settings/appearance', '/settings/display#appearance'],
        ['/settings/accessibility', '/settings/display#accessibility']
    ])('sends the former tab address %s to its section and place, %s', (pathname, canonical) => {
        expect(canonicalSettingsPath(pathname, '')).toBe(canonical);
    });

    it('sends the oldest hash addresses, /settings#<tab>, to the same place', () => {
        expect(canonicalSettingsPath('/settings', 'notifications')).toBe('/settings/alerts#notifications');
        expect(canonicalSettingsPath('/settings/', 'security')).toBe('/settings/sharing#security');
    });

    it.each([
        ['/settings/cameras', ''],
        ['/settings/identification', 'models'],
        ['/settings/data/retention', ''],
        ['/events', 'notifications'],
        ['/system-health', ''],
        ['/', '']
    ])('leaves %s#%s alone', (pathname, hash) => {
        expect(canonicalSettingsPath(pathname, hash)).toBeNull();
    });

    it('treats every canonical section address as already canonical and showing that section', () => {
        for (const section of SETTINGS_SECTION_ORDER) {
            const path = settingsSectionPath(section);
            expect(canonicalSettingsPath(path, '')).toBeNull();
            expect(settingsSectionFromRoute(path)).toBe(section);
        }
    });

    it('keeps the part a loose section address names, so a reload lands on it again', () => {
        expect(canonicalSettingsPath('/settings/sharing/', 'security')).toBe('/settings/sharing#security');
        expect(canonicalSettingsPath('/settings/identification/', 'debug')).toBe('/settings/identification#models');
        // A fragment that names no part of that section is not kept.
        expect(canonicalSettingsPath('/settings/sharing/', 'models')).toBe('/settings/sharing');
        expect(canonicalSettingsPath('/settings/sharing/', '')).toBe('/settings/sharing');
        expect(canonicalSettingsPath('/settings/sharing', 'security')).toBeNull();
    });

    it('ignores the fragment a navigation carries, so a part address is already canonical', () => {
        expect(canonicalSettingsPath('/settings/identification#models', '')).toBeNull();
    });

    it('sends the retired Enrichment address to Integrations, where its summary now lives', () => {
        expect(canonicalSettingsPath('/settings/enrichment', '')).toBe('/settings/sharing#integrations');
        expect(settingsSectionFromRoute('/settings/enrichment')).toBe('sharing');
        expect(canonicalSettingsPath('/settings', 'enrichment')).toBe('/settings/sharing#integrations');
        expect(canonicalSettingsPath('/settings/enrichment/', '')).toBe('/settings/sharing#integrations');
    });

    it('sends the retired Debug address to Models, which now holds its settings', () => {
        expect(canonicalSettingsPath('/settings/debug', '')).toBe('/settings/identification#models');
        expect(settingsSectionFromRoute('/settings/debug')).toBe('identification');
        expect(canonicalSettingsPath('/settings', 'debug')).toBe('/settings/identification#models');
    });

    it('sends every older Health address, hash or path, to the Health page', () => {
        for (const [pathname, hash] of [['/settings', 'health'], ['/settings/', 'health'], ['/settings', 'errors'], ['/settings/health', ''], ['/settings/health/', ''], ['/settings/errors', ''], ['/settings/errors/recent', '']]) {
            expect(canonicalSettingsPath(pathname, hash), `${pathname}#${hash}`).toBe('/system-health');
        }
    });

    it('settles every rewrite in one step', () => {
        for (const [pathname, hash] of [['/settings', 'ai'], ['/settings/debug', ''], ['/settings/unknown/', ''], ['/settings/', ''], ['/settings/models', '']]) {
            const canonical = canonicalSettingsPath(pathname, hash);
            expect(canonical).not.toBeNull();
            const [path, anchor = ''] = (canonical ?? '').split('#');
            expect(canonicalSettingsPath(path, anchor)).toBeNull();
        }
    });
});

describe('a part inside its section', () => {
    it('is opened by its section address with the part as the anchor', () => {
        for (const part of SETTINGS_PART_ORDER) {
            const section = settingsSectionOfPart(part);
            expect(settingsPartPath(part)).toBe(`/settings/${section}#${part}`);
            expect(settingsPartFromAnchor(section, `#${part}`)).toBe(part);
        }
    });

    it('names nothing when the anchor belongs to another section or to no part', () => {
        expect(settingsPartFromAnchor('cameras', '#models')).toBeNull();
        expect(settingsPartFromAnchor('identification', '')).toBeNull();
        expect(settingsPartFromAnchor('identification', '#nowhere')).toBeNull();
        // A retired tab's anchor names the part that holds it.
        expect(settingsPartFromAnchor('identification', '#debug')).toBe('models');
    });
});
