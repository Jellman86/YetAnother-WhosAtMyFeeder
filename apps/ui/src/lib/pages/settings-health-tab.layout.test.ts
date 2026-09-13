import { describe, expect, it } from 'vitest';
import settingsSource from './Settings.svelte?raw';
import appSource from '../../App.svelte?raw';
import tabsSource from '../components/settings/SettingsTabs.svelte?raw';
import panelSource from '../components/settings/SystemHealthPanel.svelte?raw';
import sidebarSource from '../components/Sidebar.svelte?raw';
import en from '../i18n/locales/en.json';

describe('settings health tab', () => {
    it('exposes diagnostics as a Health settings tab instead of a separate errors page', () => {
        expect(settingsSource).toContain("export type SettingsTab = 'connection' | 'detection' | 'notifications' | 'health'");
        expect(tabsSource).toContain('settings.tabs.health');
        expect(settingsSource).toContain("activeTab === 'health'");
        expect(settingsSource).toContain('<Errors />');
        expect(appSource).toContain("path === '/settings/errors'");
        expect(appSource).not.toContain("currentRoute.startsWith('/settings/errors')");
    });

    it('opens on what the host is doing, with this app named and the rest an honest remainder', () => {
        expect(settingsSource).toContain('<SystemHealthPanel />');
        expect(panelSource).toContain("fetchSystemTelemetryHistory(signal)");
        // One axis, two named series with a legend, a crosshair tooltip, and a text summary for the window.
        expect(panelSource).toContain("seriesSegments(points, 'cpu_percent', windowSeconds)");
        expect(panelSource).toContain("seriesSegments(points, 'accelerator_percent', windowSeconds)");
        expect(panelSource).toContain('data-system-health-tooltip');
        expect(panelSource).toContain('data-system-health-summary');
        // A host whose counters cannot be read says so, in words, instead of drawing nothing.
        expect(panelSource).toContain('data-system-health-cpu-unmeasured');
        expect(panelSource).toContain('data-system-health-no-accelerator');
        expect(en.settings.system_health.cpu_unmeasured).toContain('cannot be measured');
        // The keyboard's crosshair is a real range control, not a focusable picture.
        expect(panelSource).toContain('data-system-health-scrub');
        expect(panelSource).toContain('type="range"');
        // The remainder is a row of its own, hatched as well as grey, and says why it has no name.
        expect(panelSource).toContain("other_host: 'system-health-hatched'");
        expect(en.settings.system_health.role_other_host_note).toContain('Cannot be named');
        expect(sidebarSource).toContain("navigateAndClose('/settings/health')");
        expect(sidebarSource).toContain('{#if authStore.showSettings}\n                <a');
        expect(sidebarSource).toContain('{#snippet statusCard(linked: boolean)}');
        expect(en.status.open_health).toBe('System health');
    });
});
