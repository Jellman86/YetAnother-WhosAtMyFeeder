import { describe, expect, it } from 'vitest';
import { canonicalSettingsPath, settingsTabFromRoute, settingsTabPath } from './settings-route';

describe('settingsTabFromRoute', () => {
    it.each([
        [undefined, 'connection'],
        ['', 'connection'],
        ['/settings', 'connection'],
        ['/settings/', 'connection'],
        ['/settings/notifications', 'notifications'],
        ['/settings/notifications/', 'notifications'],
        ['/settings/data/retention', 'data'],
        ['/settings/errors', 'health'],
        ['/settings/errors/recent', 'health'],
        ['/settings/health', 'health'],
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
        ['/settings/errors', '', '/settings/health'],
        ['/settings/errors/recent', '', '/settings/health'],
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
        ['/', '']
    ])('leaves %s#%s alone', (pathname, hash) => {
        expect(canonicalSettingsPath(pathname, hash)).toBeNull();
    });

    it('treats every canonical tab address as already canonical and showing that tab', () => {
        const tabs = ['connection', 'detection', 'notifications', 'health', 'integrations', 'enrichment', 'ai', 'security', 'data', 'appearance', 'accessibility', 'beta', 'debug'] as const;
        for (const tab of tabs) {
            const path = settingsTabPath(tab);
            expect(canonicalSettingsPath(path, '')).toBeNull();
            expect(settingsTabFromRoute(path)).toBe(tab);
        }
    });

    it('settles every rewrite in one step', () => {
        for (const [pathname, hash] of [['/settings', 'ai'], ['/settings/errors', ''], ['/settings/unknown/', ''], ['/settings/', '']]) {
            const canonical = canonicalSettingsPath(pathname, hash);
            expect(canonical).not.toBeNull();
            expect(canonicalSettingsPath(canonical ?? '', '')).toBeNull();
        }
    });
});
