import { describe, expect, it } from 'vitest';
import settingsSource from './Settings.svelte?raw';
import appSource from '../../App.svelte?raw';
import tabsSource from '../components/settings/SettingsTabs.svelte?raw';

describe('settings health tab', () => {
    it('exposes diagnostics as a Health settings tab instead of a separate errors page', () => {
        expect(settingsSource).toContain("export type SettingsTab = 'connection' | 'detection' | 'notifications' | 'health'");
        expect(tabsSource).toContain('settings.tabs.health');
        expect(settingsSource).toContain("activeTab === 'health'");
        expect(settingsSource).toContain('<Errors />');
        expect(appSource).toContain("path === '/settings/errors'");
        expect(appSource).not.toContain("currentRoute.startsWith('/settings/errors')");
    });
});
