import { describe, expect, it } from 'vitest';

import settingsPageSource from './Settings.svelte?raw';
import appShellSource from '../../App.svelte?raw';

// Glob every Svelte / TypeScript source file (excluding tests) so the
// project-wide deep-link regression guard can scan them. Using Vite's
// import.meta.glob avoids node:fs typing issues in the Svelte tsconfig.
const allUiSources = import.meta.glob<string>(
    [
        '/src/**/*.svelte',
        '/src/**/*.ts',
        '!/src/**/*.test.ts'
    ],
    { eager: true, query: '?raw', import: 'default' }
);

describe('settings route split (roadmap 5.1)', () => {
    it('derives activeTab from the currentRoute prop instead of holding it in component state', () => {
        expect(settingsPageSource).toContain('let activeTab = $derived<SettingsTab>(tabFromRoute(currentRoute));');
        expect(settingsPageSource).not.toContain("let activeTab = $state<SettingsTab>('connection');");
    });

    it('navigates rather than mutating state on tab change', () => {
        expect(settingsPageSource).toContain('function handleTabChange(tab: SettingsTab) {');
        expect(settingsPageSource).toContain('const path = `/settings/${tab}`;');
        expect(settingsPageSource).not.toContain("`/settings#${tab}`");
    });

    it('canonicalises bare /settings, /settings/, /settings#<tab>, and unknown tabs through a single helper', () => {
        // The single helper handles every entry point so we can add new cases
        // (deep sub-paths, future locales) in one place.
        expect(settingsPageSource).toContain('function canonicalSettingsPath(pathname: string, hash: string): string | null {');
        expect(settingsPageSource).toContain("if (pathname === '/settings/' || pathname === '/settings') {");
        expect(settingsPageSource).toContain("return '/settings/connection';");
        expect(settingsPageSource).toContain("if (pathname === '/settings/errors' || pathname.startsWith('/settings/errors/')) {");
    });

    it('routes the canonicalisation through a reactive $effect so popstate / back-button URLs self-heal', () => {
        // Without the reactive guard a user clicking back to /settings/foo (a bookmark
        // they had pre-rewrite) would see the connection tab body while the URL still
        // showed foo — silent mismatch.
        expect(settingsPageSource).toContain('Self-heal non-canonical routes');
        expect(settingsPageSource).toContain('const canonical = canonicalSettingsPath(currentRoute, window.location.hash.slice(1));');
        expect(settingsPageSource).toContain("if (canonical && canonical !== currentRoute) {");
    });

    it('App passes currentRoute into Settings so the derived tab tracks the URL', () => {
        expect(appShellSource).toContain('<Settings onNavigate={navigate} {currentRoute} />');
    });

    it('no source file under apps/ui/src emits the legacy /settings#<tab> form', () => {
        // Project-wide regression guard: any future feature that adds a hash-form
        // deep link will trip this check. The Settings.svelte comment block
        // referencing the legacy form is allowed.
        const offenders: string[] = [];
        for (const [path, content] of Object.entries(allUiSources)) {
            if (path.endsWith('Settings.svelte')) continue; // legacy comment lives here
            if (!/['"`]\/settings#[a-z][a-z_-]*/.test(content)) continue;
            offenders.push(path);
        }
        expect(offenders).toEqual([]);
    });
});
