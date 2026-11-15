import { describe, expect, it } from 'vitest';
import tabsSource from './SettingsTabs.svelte?raw';
import pageSource from './_primitives/SettingsPage.svelte?raw';
import advancedSource from './_primitives/AdvancedSection.svelte?raw';
import segmentedSource from './_primitives/SettingsSegmented.svelte?raw';
import cardSource from './_primitives/SettingsCard.svelte?raw';
import gardenSource from './GardenBetaSettings.svelte?raw';
import integrationSource from './IntegrationSettings.svelte?raw';
import authenticationSource from './AuthenticationSettings.svelte?raw';
import modelManagerSource from '../../pages/models/ModelManager.svelte?raw';
import telemetrySource from './TelemetrySettings.svelte?raw';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';

const appCss = readFileSync(new URL('../../../app.css', import.meta.url), 'utf8');

// Every Settings tab, read together: one look for the same thing on every tab.
const tabSources = import.meta.glob<string>(['./*.svelte', '../../pages/models/ModelManager.svelte'], {
    query: '?raw',
    import: 'default',
    eager: true
});

describe('Settings has one look across tabs', () => {
    it('marks the current section the way the sidebar does, never with a bar on one edge, at 44 px', () => {
        expect(tabsSource).not.toContain('border-l-2');
        expect(tabsSource).toContain('sidebar-nav-active');
        expect(tabsSource).toMatch(/class="sidebar-nav /);
        expect(tabsSource).not.toContain('min-h-10');
    });

    it('draws every chosen option with the kit\'s one selected style', () => {
        // A neutral track with the chosen segment raised; no solid fill and no tick.
        expect(segmentedSource).toContain('rounded-xl bg-slate-100 p-1 dark:bg-slate-800');
        expect(segmentedSource).toContain('bg-surface font-semibold text-slate-900 shadow-sm');
        expect(segmentedSource).not.toContain('bg-brand-700');
        expect(segmentedSource).not.toContain('m5 12 4 4 10-10');
        // Four or more choices, or choices that need a sentence, are a select or a radio list.
        expect(segmentedSource).toContain("options.length >= 4 ? 'select' : 'track'");
        for (const [file, source] of Object.entries(tabSources)) {
            expect(source, file).not.toContain('border-brand-400 bg-brand-100/70');
            expect(source, file).not.toContain('model-card-selected');
            expect(source, file).not.toMatch(/bg-brand-700[^'"]*text-white[^'"]*'\s*:/);
        }
        expect(modelManagerSource).toContain('choice-active');
    });

    it('uses switches for on/off settings; a checkbox only acknowledges a warning', () => {
        for (const [file, source] of Object.entries(tabSources)) {
            if (file.endsWith('NativeProfileRevalidation.svelte')) continue;
            expect(source, file).not.toContain('type="checkbox"');
        }
    });

    it('moves thresholds with one control, the slider, on every tab', () => {
        expect(gardenSource).toContain('<SettingsSlider');
        expect(gardenSource).not.toMatch(/type="number"[^>]*garden-(motion-confidence|naming-threshold)/s);
    });

    it('never repeats a card title as the label of the row below it', () => {
        // The switch for a whole card sits in its header, named by the card title.
        expect(cardSource).toContain('titleId');
        for (const service of ['birdnet', 'inaturalist', 'ebird', 'birdweather', 'ha-weather']) {
            expect(integrationSource, service).toContain(`titleId="integration-${service}-title"`);
        }
        expect(authenticationSource).toContain('titleId="security-auth-title"');
        // Telemetry's first switch is named for what it sends, not after the section.
        expect(telemetrySource).toContain("label={$_('settings.telemetry.usage_title'");
        expect(telemetrySource).not.toContain("label={$_('settings.telemetry.title')}");
    });

    it('draws no colour bar along one edge of a note', () => {
        for (const [file, source] of Object.entries(tabSources)) {
            expect(source, file).not.toMatch(/\bborder-l-[24]\b/);
        }
    });

    it('ends every two-column control on the right edge, a switch included', () => {
        const columns = appCss.slice(appCss.indexOf('@utility settings-row-columns'));
        expect(columns.slice(0, columns.indexOf('\n}\n'))).toMatch(/\.switch-track:first-child \{\s*display: flex;\s*margin-inline-start: auto;/);
    });

    it('shows no "Advanced" chip: a disclosure is named by its own title', () => {
        expect(advancedSource).not.toContain("settings.common.advanced'");
        expect(advancedSource).not.toContain('eyebrow rounded-md border');
    });

    it('keeps the focused control clear of the sticky save bar', () => {
        expect(pageSource).toContain('scrollPaddingBottom');
        expect(pageSource).toContain('ResizeObserver');
    });

    it('says once, on every tab, that buttons act at once and fields wait for Save', () => {
        expect(pageSource).toContain('data-settings-save-rule');
    });
});
