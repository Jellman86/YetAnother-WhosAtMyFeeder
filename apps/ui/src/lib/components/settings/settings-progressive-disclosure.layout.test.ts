import { describe, expect, it } from 'vitest';

import accessibilitySource from './AccessibilitySettings.svelte?raw';
import aiSource from './AISettings.svelte?raw';
import appearanceSource from './AppearanceSettings.svelte?raw';
import authenticationSource from './AuthenticationSettings.svelte?raw';
import connectionSource from './ConnectionSettings.svelte?raw';
import dataSource from './DataSettings.svelte?raw';
import maintenanceSource from './MaintenanceSettings.svelte?raw';
import detectionSource from './DetectionSettings.svelte?raw';
import modelSource from './ModelSettings.svelte?raw';
import enrichmentSource from './EnrichmentSettings.svelte?raw';
import integrationSource from './IntegrationSettings.svelte?raw';
import notificationSource from './NotificationSettings.svelte?raw';
import advancedSectionSource from './_primitives/AdvancedSection.svelte?raw';
import settingsCardSource from './_primitives/SettingsCard.svelte?raw';
import healthSource from '../../pages/Errors.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';
import sharingSource from './sections/SharingSection.svelte?raw';

const settingsSources = [
    accessibilitySource,
    aiSource,
    appearanceSource,
    authenticationSource,
    connectionSource,
    dataSource,
    maintenanceSource,
    detectionSource,
    modelSource,
    enrichmentSource,
    integrationSource,
    notificationSource,
    healthSource,
    settingsPageSource
];

describe('Settings progressive disclosure', () => {
    it('reveals dependent configuration only after its feature is enabled', () => {
        expect(aiSource.indexOf('{#if llmEnabled}')).toBeLessThan(aiSource.indexOf('labelId="setting-llm-provider"'));
        expect(authenticationSource.indexOf('{#if authEnabled}')).toBeLessThan(authenticationSource.indexOf('labelId="setting-auth-username"'));
        expect(authenticationSource.indexOf('{#if publicAccessEnabled}')).toBeLessThan(authenticationSource.indexOf('labelId="setting-public-show-cameras"'));

        for (const [enabled, firstField] of [
            ['birdnetEnabled', 'setting-birdnet-url'],
            ['inaturalistEnabled', 'setting-inat-client-id'],
            ['ebirdEnabled', 'setting-ebird-api-key'],
            ['birdweatherEnabled', 'setting-birdweather-token']
        ]) {
            expect(integrationSource.indexOf(`{#if ${enabled}}`)).toBeLessThan(integrationSource.indexOf(firstField));
        }

        for (const channel of ['discord', 'pushover', 'telegram', 'email']) {
            expect(notificationSource).toContain(`{#if ${channel}Enabled}`);
        }
        expect(notificationSource).toContain('items-start');
    });

    it('keeps optional, analytical, and destructive work out of the default hierarchy', () => {
        // Telemetry is what leaves the installation, so it sits with Security, beside who can reach it.
        expect(connectionSource).not.toContain('settings.telemetry.title');
        const security = sharingSource.slice(sharingSource.indexOf('data-settings-part="security"'));
        expect(security).toContain('<TelemetrySettings');
        expect(aiSource).toContain('id="ai-usage"');
        expect(appearanceSource).toContain('id="appearance-typography-and-colour"');
        // Repairs and deletions have their own tab; the deletions are the last section, a plain
        // heading like every other, each behind its own confirmation.
        expect(dataSource).not.toContain('id="data-danger"');
        expect(maintenanceSource).toContain('id="data-danger"');
        expect(maintenanceSource).not.toMatch(/<SettingsCard\s+collapsible/);
        expect(dataSource).not.toContain('settings.data.setup_wizard_title');
        expect(maintenanceSource.indexOf('id="data-danger"')).toBeLessThan(maintenanceSource.indexOf('settings.danger.reset_desc'));
        // Testing the models is one row that opens Model evaluation, not a section of its own.
        expect(modelSource).toContain('labelId="setting-model-evaluation"');
        expect(modelSource).not.toContain('id="models-testing"');
        expect(modelSource).toContain('<SettingsToggle');
        expect(settingsPageSource).not.toContain('role="switch"');
        expect(advancedSectionSource).toContain('openByDefault?: boolean');
    });

    it('uses a calm, readable card hierarchy on every audited tab', () => {
        expect(settingsCardSource).not.toContain('icon?: string');
        expect(settingsCardSource).not.toContain('{icon}');
        expect(settingsCardSource).toContain('text-sm leading-relaxed');
        expect(enrichmentSource).toContain('divide-y divide-line-soft');
        expect(enrichmentSource).not.toContain('grid grid-cols-1 md:grid-cols-2 gap-4');

        for (const source of settingsSources) {
            expect(source).not.toMatch(/text-\[(8|9|10|11)px\]/);
            expect(source).not.toMatch(/<SettingsCard[^>]*\bicon=/s);
        }
    });
});
