import { lazyComponent } from '../../../app/lazy-component';
import type { SettingsPart } from '../../../settings/settings-route';

// Each part's code loads when its section first opens. The drafts stay on the Settings page, so a
// part's edits survive leaving its section. The page also waits on these to land on a field.
export const loadConnectionSettings = lazyComponent(() => import('../ConnectionSettings.svelte'));
export const loadBirdnetSettings = lazyComponent(() => import('../BirdnetSettings.svelte'));
export const loadDetectionSettings = lazyComponent(() => import('../DetectionSettings.svelte'));
export const loadModelSettings = lazyComponent(() => import('../ModelSettings.svelte'));
export const loadHardwareSettings = lazyComponent(() => import('../HardwareSettings.svelte'));
export const loadNamingSettings = lazyComponent(() => import('../NamingSettings.svelte'));
export const loadVisitGapSettings = lazyComponent(() => import('../VisitGapSettings.svelte'));
export const loadGardenBetaSettings = lazyComponent(() => import('../GardenBetaSettings.svelte'));
export const loadNotificationSettings = lazyComponent(() => import('../NotificationSettings.svelte'));
export const loadNotificationChannelsSettings = lazyComponent(() => import('../NotificationChannelsSettings.svelte'));
export const loadGardenNotificationSettings = lazyComponent(() => import('../GardenNotificationSettings.svelte'));
export const loadIntegrationSettings = lazyComponent(() => import('../IntegrationSettings.svelte'));
export const loadEnrichmentSettings = lazyComponent(() => import('../EnrichmentSettings.svelte'));
export const loadHaWeatherSettings = lazyComponent(() => import('../HaWeatherSettings.svelte'));
export const loadLocationSettings = lazyComponent(() => import('../LocationSettings.svelte'));
export const loadAiSettings = lazyComponent(() => import('../AISettings.svelte'));
export const loadAuthenticationSettings = lazyComponent(() => import('../AuthenticationSettings.svelte'));
export const loadTelemetrySettings = lazyComponent(() => import('../TelemetrySettings.svelte'));
export const loadDataSettings = lazyComponent(() => import('../DataSettings.svelte'));
export const loadMaintenanceSettings = lazyComponent(() => import('../MaintenanceSettings.svelte'));
export const loadDangerZoneSettings = lazyComponent(() => import('../DangerZoneSettings.svelte'));
export const loadAppearanceSettings = lazyComponent(() => import('../AppearanceSettings.svelte'));
export const loadUnitsSettings = lazyComponent(() => import('../UnitsSettings.svelte'));
export const loadAccessibilitySettings = lazyComponent(() => import('../AccessibilitySettings.svelte'));

/** Everything a part needs loaded before it has its full height. */
export const SETTINGS_PART_LOADERS: Readonly<Record<SettingsPart, () => Promise<unknown>>> = {
    connection: () => Promise.all([loadConnectionSettings(), loadBirdnetSettings()]),
    detection: () => Promise.all([loadNamingSettings(), loadVisitGapSettings(), loadDetectionSettings()]),
    models: () => Promise.all([loadModelSettings(), loadHardwareSettings()]),
    beta: loadGardenBetaSettings,
    notifications: () => Promise.all([loadNotificationSettings(), loadNotificationChannelsSettings()]),
    integrations: () => Promise.all([loadIntegrationSettings(), loadHaWeatherSettings(), loadEnrichmentSettings()]),
    ai: () => Promise.all([loadAiSettings(), loadTelemetrySettings()]),
    security: () => Promise.all([loadLocationSettings(), loadAuthenticationSettings()]),
    data: loadDataSettings,
    maintenance: () => Promise.all([loadMaintenanceSettings(), loadDangerZoneSettings()]),
    appearance: loadAppearanceSettings,
    accessibility: loadAccessibilitySettings
};
