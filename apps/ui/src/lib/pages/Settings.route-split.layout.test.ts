import { describe, expect, it } from 'vitest';

import settingsPageSource from './Settings.svelte?raw';
import appShellSource from '../../App.svelte?raw';

describe('settings route split (#33 follow-up)', () => {
    it('derives activeTab from the currentRoute prop instead of holding it in component state', () => {
        expect(settingsPageSource).toContain('let activeTab = $derived<SettingsTab>(tabFromRoute(currentRoute));');
        expect(settingsPageSource).not.toContain("let activeTab = $state<SettingsTab>('connection');");
    });

    it('navigates rather than mutating state on tab change', () => {
        expect(settingsPageSource).toContain('function handleTabChange(tab: SettingsTab) {');
        expect(settingsPageSource).toContain('const path = `/settings/${tab}`;');
        expect(settingsPageSource).not.toContain("`/settings#${tab}`");
    });

    it('canonicalises /settings and /settings#<tab> to /settings/<tab>', () => {
        expect(settingsPageSource).toContain("onNavigate(`/settings/${hash}`, { replace: true });");
        expect(settingsPageSource).toContain("onNavigate('/settings/connection', { replace: true });");
    });

    it('App passes currentRoute into Settings so the derived tab tracks the URL', () => {
        expect(appShellSource).toContain('<Settings onNavigate={navigate} {currentRoute} />');
    });

    it('does not emit any /settings#<tab> deep links from job/notification surfaces', () => {
        // Catches regressions where a future feature reintroduces the hash form.
        expect(settingsPageSource).not.toMatch(/'\/settings#[a-z]+'/);
    });
});
