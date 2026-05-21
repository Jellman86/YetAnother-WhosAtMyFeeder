import { describe, expect, it } from 'vitest';
import telemetryBannerSource from './TelemetryBanner.svelte?raw';

describe('TelemetryBanner', () => {
    it('reacts after settings load instead of only checking during mount', () => {
        expect(telemetryBannerSource).toContain('$effect(() => {');
        expect(telemetryBannerSource).toContain('const settings = settingsStore.settings;');
        expect(telemetryBannerSource).toContain('if (wasDismissed || !settings) return;');
        expect(telemetryBannerSource).toContain('isDismissed = Boolean(settings.telemetry_enabled);');
    });

    it('persists dismissal in state and local storage', () => {
        expect(telemetryBannerSource).toContain('wasDismissed = true;');
        expect(telemetryBannerSource).toContain("localStorage.setItem(DISMISSED_KEY, 'true');");
    });
});
