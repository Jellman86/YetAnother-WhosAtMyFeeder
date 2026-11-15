import { describe, expect, it } from 'vitest';
import { canonicalSettingsPath, SETTINGS_TAB_ORDER, settingsTabFromRoute, settingsTabPath } from './settings-route';

describe('settingsTabFromRoute', () => {
    it.each([
        [undefined, 'connection'],
        ['', 'connection'],
        ['/settings', 'connection'],
        ['/settings/', 'connection'],
        ['/settings/notifications', 'notifications'],
        ['/settings/notifications/', 'notifications'],
        ['/settings/data/retention', 'data'],
        ['/settings/models', 'models'],
        ['/settings/maintenance', 'maintenance'],
        ['/settings/not-a-tab', 'connection'],
        ['/events', 'connection']
    ] as const)('shows %s as the %s tab', (route, tab) => {
        expect(settingsTabFromRoute(route)).toBe(tab);
    });
});

describe('canonicalSettingsPath', () => {
    it.each([
        ['/settings', '', '/settings/connection'],
        ['/settings/', '', '/settings/connection'],
        ['/settings', 'notifications', '/settings/notifications'],
        ['/settings/', 'security', '/settings/security'],
        ['/settings', 'not-a-tab', '/settings/connection'],
        ['/settings/not-a-tab', '', '/settings/connection'],
        ['/settings/ai/', '', '/settings/ai']
    ])('rewrites the legacy or loose address %s#%s to %s', (pathname, hash, canonical) => {
        expect(canonicalSettingsPath(pathname, hash)).toBe(canonical);
    });

    it.each([
        ['/settings/connection', ''],
        ['/settings/beta', 'detection'],
        ['/settings/data/retention', ''],
        ['/events', 'notifications'],
        ['/system-health', ''],
        ['/', '']
    ])('leaves %s#%s alone', (pathname, hash) => {
        expect(canonicalSettingsPath(pathname, hash)).toBeNull();
    });

    it('treats every canonical tab address as already canonical and showing that tab', () => {
        for (const tab of SETTINGS_TAB_ORDER) {
            const path = settingsTabPath(tab);
            expect(canonicalSettingsPath(path, '')).toBeNull();
            expect(settingsTabFromRoute(path)).toBe(tab);
        }
    });

    it('has one tab per job: models apart from detection, maintenance apart from data, and no status pages', () => {
        expect(SETTINGS_TAB_ORDER).toEqual([
            'connection', 'detection', 'models',
            'integrations', 'ai', 'notifications',
            'security', 'data', 'maintenance', 'beta',
            'appearance', 'accessibility'
        ]);
        // Health is a page of its own, and Debug's two settings moved into Models.
        expect(SETTINGS_TAB_ORDER).not.toContain('health');
        expect(SETTINGS_TAB_ORDER).not.toContain('debug');
    });

    it('sends the retired Enrichment address to Integrations, where its summary now lives', () => {
        expect(canonicalSettingsPath('/settings/enrichment', '')).toBe('/settings/integrations');
        expect(settingsTabFromRoute('/settings/enrichment')).toBe('integrations');
        expect(canonicalSettingsPath('/settings', 'enrichment')).toBe('/settings/integrations');
        expect(canonicalSettingsPath('/settings/', 'enrichment')).toBe('/settings/integrations');
        expect(canonicalSettingsPath('/settings/enrichment/', '')).toBe('/settings/integrations');
    });

    it('sends the retired Debug address to Models, which now holds its settings', () => {
        expect(canonicalSettingsPath('/settings/debug', '')).toBe('/settings/models');
        expect(settingsTabFromRoute('/settings/debug')).toBe('models');
        expect(canonicalSettingsPath('/settings', 'debug')).toBe('/settings/models');
    });

    it('settles every rewrite in one step', () => {
        for (const [pathname, hash] of [['/settings', 'ai'], ['/settings/debug', ''], ['/settings/unknown/', ''], ['/settings/', '']]) {
            const canonical = canonicalSettingsPath(pathname, hash);
            expect(canonical).not.toBeNull();
            expect(canonicalSettingsPath(canonical ?? '', '')).toBeNull();
        }
    });
});
