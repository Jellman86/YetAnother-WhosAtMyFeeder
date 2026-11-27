import { describe, expect, it } from 'vitest';
import tabsSource from './SettingsTabs.svelte?raw';
import pageSource from './_primitives/SettingsPage.svelte?raw';
import advancedSource from './_primitives/AdvancedSection.svelte?raw';
import segmentedSource from './_primitives/SettingsSegmented.svelte?raw';
import sharedSegmentedSource from '../ui/Segmented.svelte?raw';
import cardSource from './_primitives/SettingsCard.svelte?raw';
import gardenSource from './GardenBetaSettings.svelte?raw';
import integrationSource from './IntegrationSettings.svelte?raw';
import haWeatherSource from './HaWeatherSettings.svelte?raw';
import birdnetSource from './BirdnetSettings.svelte?raw';
import authenticationSource from './AuthenticationSettings.svelte?raw';
import modelManagerSource from '../../pages/models/ModelManager.svelte?raw';
import telemetrySource from './TelemetrySettings.svelte?raw';
import connectionSource from './ConnectionSettings.svelte?raw';
import notificationRulesSource from './NotificationSettings.svelte?raw';
import notificationChannelsSource from './NotificationChannelsSettings.svelte?raw';

// Alerts' rules and its channels are two components; these checks read them as one.
const notificationSource = `${notificationRulesSource}\n${notificationChannelsSource}`;
import rangeFilterSource from './RangeFilterSettings.svelte?raw';
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
        // The shared choose-one track (ui/Segmented): a neutral track, the chosen segment raised, set
        // semibold and checked, so it never reads by tint alone; no solid brand fill.
        expect(segmentedSource).toContain('<Segmented');
        expect(sharedSegmentedSource).toContain('rounded-xl bg-surface-raised p-1');
        expect(sharedSegmentedSource).toContain('bg-surface font-semibold text-strong');
        expect(sharedSegmentedSource).toContain('data-segment-check');
        expect(sharedSegmentedSource).toContain('aria-pressed={chosen}');
        expect(segmentedSource + sharedSegmentedSource).not.toContain('bg-brand-700');
        expect(sharedSegmentedSource).not.toContain('bg-accent ');
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
        expect(birdnetSource).toContain('titleId="integration-birdnet-title"');
        for (const service of ['inaturalist', 'ebird', 'birdweather']) {
            expect(integrationSource, service).toContain(`titleId="integration-${service}-title"`);
        }
        expect(haWeatherSource).toContain('titleId="integration-ha-weather-title"');
        expect(authenticationSource).toContain('titleId="security-auth-title"');
        // Telemetry's first switch is named for what it sends, not after the section.
        expect(telemetrySource).toContain("label={$_('settings.telemetry.usage_title'");
        expect(telemetrySource).not.toContain("label={$_('settings.telemetry.title')}");
    });

    it('reads in the app\'s own fonts, like every other page', () => {
        expect(appCss).not.toContain('settings-ui');
        expect(appCss).not.toContain('--font-ui');
        expect(pageSource).not.toMatch(/font-(sans|serif|mono|ui|body)\b/);
        for (const [file, source] of Object.entries(tabSources)) {
            expect(source, file).not.toMatch(/font-family|font-\[/);
        }
    });

    it('lists the notification channels as rows of one Channels card, each with its switch on the right', () => {
        expect(notificationSource).toContain("$_('settings.notifications.channels_title'");
        for (const channel of ['discord', 'pushover', 'telegram', 'email']) {
            expect(notificationSource, channel).toContain(`data-notification-channel="${channel}"`);
            expect(notificationSource, channel).not.toContain(`titleId="${channel}-channel-label"`);
        }
    });

    it('keeps how the range filter decides behind a plain disclosure, closed at first', () => {
        expect(rangeFilterSource).toContain("$_('settings.range_filter.how_toggle'");
        expect(rangeFilterSource).toContain('aria-expanded={howOpen}');
        expect(rangeFilterSource).toContain('let howOpen = $state(false);');
        const disclosure = rangeFilterSource.indexOf('{#if howOpen}');
        expect(disclosure).toBeGreaterThan(-1);
        expect(rangeFilterSource.indexOf("settings.range_filter.how_fallback")).toBeGreaterThan(disclosure);
    });

    it('draws every loading spinner, so waiting is never shown as an empty space', () => {
        for (const [file, source] of Object.entries(tabSources)) {
            // A spinning ring (a div or span) is drawn only by its border; an SVG spinner draws itself.
            for (const ring of source.match(/<(div|span)\b[^>]*class="[^"]*\banimate-spin\b[^"]*"/g) ?? []) {
                expect(ring, file).toMatch(/border-\d/);
            }
        }
    });

    it('draws no colour bar along one edge of a note', () => {
        for (const [file, source] of Object.entries(tabSources)) {
            expect(source, file).not.toMatch(/\bborder-l-[24]\b/);
            expect(source, file).not.toContain('class=""');
        }
    });

    it('ends every two-column control on the right edge, a switch included', () => {
        const columns = appCss.slice(appCss.indexOf('@utility settings-row-columns'));
        expect(columns.slice(0, columns.indexOf('\n}\n'))).toMatch(/\.switch-track:first-child \{\s*display: flex;\s*margin-inline-start: auto;/);
    });

    it('names a disclosure "Show advanced options · title", never in nested brackets', () => {
        expect(advancedSource).toContain("{' · '}");
        expect(advancedSource).not.toContain('({title})');
        expect(connectionSource).toContain("default: 'Full clips' })");
    });

    it('shows no "Advanced" chip: a disclosure is named by its own title', () => {
        expect(advancedSource).not.toContain("settings.common.advanced'");
        expect(advancedSource).not.toContain('eyebrow rounded-md border');
    });

    it('keeps the focused control clear of the sticky save bar', () => {
        expect(pageSource).toContain('scrollPaddingBottom');
        expect(pageSource).toContain('ResizeObserver');
    });

    it('says that buttons act at once and fields wait for Save in the save details, not above every tab', () => {
        const details = pageSource.indexOf('data-settings-save-details\n');
        const rule = pageSource.indexOf('data-settings-save-rule>');
        expect(rule).toBeGreaterThan(details);
        expect(rule).toBeLessThan(pageSource.indexOf('data-settings-save-bar'));
        expect(pageSource.indexOf('data-settings-save-rule>', rule + 1)).toBe(-1);
    });

    it('keeps the save bar to one line: the count, Details, Discard and Save; everything else waits in the details', () => {
        // The rule, the sections, conflicts and refusals filled two thirds of a phone at 200% text in the bar.
        const bar = pageSource.slice(pageSource.indexOf('data-settings-save-bar'), pageSource.indexOf('</section>', pageSource.indexOf('data-settings-save-bar')));
        expect(bar).toContain('data-save-summary');
        expect(bar).toContain('aria-controls="settings-save-details"');
        for (const kept of ['data-settings-save-rule', 'data-draft-conflicts', 'data-save-problem', 'data-restored-draft', 'onOpenTab?.(tab.id)']) {
            expect(bar, kept).not.toContain(kept);
        }
        // The details open by themselves for anything that needs a decision, and while they are
        // held open the button only goes to them, named so, with no expanded state to claim.
        expect(pageSource).toContain('const detailsHeldOpen = $derived(conflicts.length > 0 || problemShown || Boolean(restoredNotice));');
        expect(pageSource).toContain('const detailsShown = $derived(detailsOpen || detailsHeldOpen);');
        expect(bar).toContain("aria-expanded={detailsHeldOpen ? undefined : detailsShown}");
        expect(bar).toContain("settings.save_bar.go_to_details");
    });
});
