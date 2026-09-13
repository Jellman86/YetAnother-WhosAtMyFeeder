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
        // One axis, a named line per readable device with a legend, a crosshair tooltip,
        // and a text summary for the window.
        expect(panelSource).toContain('chartSeries(history, cpuLabel)');
        expect(panelSource).toContain('seriesSegments(points, line.load, windowSeconds)');
        expect(panelSource).toContain('data-system-health-tooltip');
        expect(panelSource).toContain('data-system-health-summary');
        // Every line says what its number covers: a GPU inside a container is this app's work only.
        expect(panelSource).toContain('scopeNote(line.scope)');
        expect(en.settings.system_health.scope_app).toBe('this app only');
        expect(en.settings.system_health.app_scope_note).toContain('not visible here');
        // A device that is present but unmeasurable is named rather than silently missing.
        expect(panelSource).toContain('unreadableAccelerators(history)');
        expect(en.settings.system_health.unreadable_nvidia).toContain('no utilisation counter');
        // A host whose counters cannot be read says so, in words, instead of drawing nothing.
        expect(panelSource).toContain('data-system-health-cpu-unmeasured');
        expect(panelSource).toContain('data-system-health-no-accelerator');
        expect(en.settings.system_health.cpu_unmeasured).toContain('cannot be measured');
        // The keyboard's crosshair is a real range control, not a focusable picture, and it
        // stays out of sight until focused so it is not a handle attached to nothing.
        expect(panelSource).toContain('data-system-health-scrub');
        expect(panelSource).toContain('type="range"');
        expect(panelSource).toContain('.system-health-scrub:focus-visible');
        expect(panelSource).toContain('aria-valuetext={inspectedSpoken}');
        // The inspected sample is marked on each line, so the crosshair belongs to something.
        expect(panelSource).toContain('data-system-health-marker');
        // The remainder is a row of its own, hatched as well as grey, and says why it has no name.
        expect(panelSource).toContain("other_host: 'system-health-hatched'");
        expect(en.settings.system_health.role_other_host_note).toContain('Cannot be named');
        expect(sidebarSource).toContain("navigateAndClose('/settings/health')");
        expect(sidebarSource).toContain('{#if authStore.showSettings}\n                <a');
        expect(sidebarSource).toContain('{#snippet statusCard(linked: boolean)}');
        expect(en.status.open_health).toBe('System health');
    });
});
