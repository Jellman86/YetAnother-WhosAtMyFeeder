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

describe('the seven Settings sections', () => {
    it('are organised by the task an owner comes to do, in that order', () => {
        expect(SETTINGS_SECTION_ORDER).toEqual(['cameras', 'identification', 'integrations', 'notifications', 'access', 'storage', 'display']);
    });

    it('hold every part exactly once, and no status pages', () => {
        expect(SETTINGS_SECTION_PARTS).toEqual({
            cameras: ['connection', 'location'],
            identification: ['detection', 'models', 'beta'],
            integrations: ['birdnet', 'weather', 'networks', 'ai', 'enrichment'],
            notifications: ['rules', 'channels', 'garden-alerts'],
            access: ['security', 'telemetry'],
            storage: ['data', 'maintenance'],
            display: ['appearance', 'accessibility']
        });
        // No part is in two sections.
        expect(new Set(SETTINGS_PART_ORDER).size).toBe(SETTINGS_PART_ORDER.length);
        expect(SETTINGS_PART_ORDER).toHaveLength(19);
        // No name is both a section and a part, so an address never means two things.
        expect(SETTINGS_PART_ORDER.filter((part) => (SETTINGS_SECTION_ORDER as readonly string[]).includes(part))).toEqual([]);
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
        ['/settings/notifications', 'notifications'],
        ['/settings/notifications/', 'notifications'],
        ['/settings/alerts', 'notifications'],
        ['/settings/sharing', 'access'],
        ['/settings/sharing#integrations', 'integrations'],
        ['/settings/sharing#ai', 'integrations'],
        ['/settings/sharing#security', 'access'],
        ['/settings/ai', 'integrations'],
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
        ['/settings', 'notifications', '/settings/notifications'],
        ['/settings', 'alerts', '/settings/notifications'],
        ['/settings', 'sharing', '/settings/access'],
        ['/settings', 'not-a-section', '/settings/cameras'],
        ['/settings/not-a-section', '', '/settings/cameras'],
        ['/settings/access/', '', '/settings/access']
    ])('rewrites the loose address %s#%s to %s', (pathname, hash, canonical) => {
        expect(canonicalSettingsPath(pathname, hash)).toBe(canonical);
    });

    it.each([
        ['/settings/connection', '/settings/cameras#connection'],
        ['/settings/detection', '/settings/identification#detection'],
        ['/settings/models', '/settings/identification#models'],
        ['/settings/beta', '/settings/identification#beta'],
        ['/settings/ai/', '/settings/integrations#ai'],
        ['/settings/security', '/settings/access#security'],
        ['/settings/enrichment', '/settings/integrations#enrichment'],
        ['/settings/location', '/settings/cameras#location'],
        ['/settings/data', '/settings/storage#data'],
        ['/settings/maintenance', '/settings/storage#maintenance'],
        ['/settings/appearance', '/settings/display#appearance'],
        ['/settings/accessibility', '/settings/display#accessibility']
    ])('sends the former tab address %s to its section and place, %s', (pathname, canonical) => {
        expect(canonicalSettingsPath(pathname, '')).toBe(canonical);
    });

    it('sends the oldest hash addresses, /settings#<tab>, to the same place', () => {
        expect(canonicalSettingsPath('/settings', 'ai')).toBe('/settings/integrations#ai');
        expect(canonicalSettingsPath('/settings/', 'security')).toBe('/settings/access#security');
    });

    it('opens the Notifications and Integrations sections for the former tabs of those names', () => {
        for (const name of ['notifications', 'integrations']) {
            expect(canonicalSettingsPath(`/settings/${name}`, '')).toBeNull();
            expect(canonicalSettingsPath(`/settings/${name}/`, '')).toBe(`/settings/${name}`);
            expect(canonicalSettingsPath('/settings', name)).toBe(`/settings/${name}`);
        }
    });

    it.each([
        ['/settings/alerts', '', '/settings/notifications'],
        ['/settings/alerts/', '', '/settings/notifications'],
        ['/settings/alerts', 'notifications', '/settings/notifications'],
        ['/settings/alerts', 'nowhere', '/settings/notifications'],
        ['/settings/sharing', '', '/settings/access'],
        ['/settings/sharing', 'security', '/settings/access#security'],
        ['/settings/sharing', 'integrations', '/settings/integrations'],
        ['/settings/sharing/', 'integrations', '/settings/integrations'],
        ['/settings/sharing', 'ai', '/settings/integrations#ai'],
        ['/settings/sharing', '#ai', '/settings/integrations#ai']
    ])('sends the renamed section address %s#%s to %s', (pathname, hash, canonical) => {
        expect(canonicalSettingsPath(pathname, hash)).toBe(canonical);
        expect(settingsSectionFromRoute(hash ? `${pathname}#${hash.replace(/^#/, '')}` : pathname)).toBe(settingsSectionFromRoute(canonical));
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
        expect(canonicalSettingsPath('/settings/access/', 'security')).toBe('/settings/access#security');
        expect(canonicalSettingsPath('/settings/identification/', 'debug')).toBe('/settings/identification#models');
        // A fragment that names no part of that section is not kept.
        expect(canonicalSettingsPath('/settings/access/', 'models')).toBe('/settings/access');
        expect(canonicalSettingsPath('/settings/access/', '')).toBe('/settings/access');
        expect(canonicalSettingsPath('/settings/access', 'security')).toBeNull();
    });

    it('ignores the fragment a navigation carries, so a part address is already canonical', () => {
        expect(canonicalSettingsPath('/settings/identification#models', '')).toBeNull();
    });

    it('sends the retired Enrichment address to species information in Integrations', () => {
        expect(canonicalSettingsPath('/settings/enrichment', '')).toBe('/settings/integrations#enrichment');
        expect(settingsSectionFromRoute('/settings/enrichment')).toBe('integrations');
        expect(canonicalSettingsPath('/settings', 'enrichment')).toBe('/settings/integrations#enrichment');
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
        for (const [pathname, hash] of [['/settings', 'ai'], ['/settings/alerts', ''], ['/settings/sharing', 'integrations'], ['/settings/sharing', 'ai'], ['/settings/debug', ''], ['/settings/unknown/', ''], ['/settings/', ''], ['/settings/models', '']]) {
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
