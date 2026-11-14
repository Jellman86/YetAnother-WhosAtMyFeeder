import { describe, expect, it } from 'vitest';
import { settingsFieldTab } from '../../settings/settings-fields';
import settingsPageSource from '../../pages/Settings.svelte?raw';
import integrationSource from './IntegrationSettings.svelte?raw';
import aiSource from './AISettings.svelte?raw';

describe('the Settings save model', () => {
    it('gives every field the draft tracks a tab, so the save bar can name where each change is', () => {
        const tracked = [...settingsPageSource.matchAll(/\{\s*field: '(\w+)', draft:/g)].map((match) => match[1]);
        expect(tracked.length).toBeGreaterThan(150);
        expect(tracked.filter((field) => settingsFieldTab(field) === null)).toEqual([]);
    });

    it('never writes a default into the Integrations draft on its own', () => {
        // An effect that copied the location into the iNaturalist defaults made the tab unsaved on open.
        expect(integrationSource).not.toMatch(/inaturalistDefault(Lat|Lon) = locationL/);
        expect(integrationSource).not.toMatch(/inaturalistDefaultPlace = result/);
    });

    it('has one save: the AI tab offers no second apply button', () => {
        expect(aiSource).not.toContain('llm_prompt_apply_style');
        expect(aiSource).not.toContain('llm_prompt_reset_defaults');
    });

    it('reports each result once, with no banner copying the notification', () => {
        expect(settingsPageSource).not.toMatch(/\bmessage = \{/);
        expect(settingsPageSource).not.toContain('{message}');
    });
});

describe('the save bar announcements', () => {
    it('keeps the polite summary and the save problem alert as separate, un-nested regions', async () => {
        const { default: pageSource } = await import('./_primitives/SettingsPage.svelte?raw');
        const summaryAt = pageSource.indexOf('aria-live="polite" data-save-summary');
        const problemAt = pageSource.indexOf('role="alert" data-save-problem');
        expect(summaryAt).toBeGreaterThan(-1);
        expect(problemAt).toBeGreaterThan(summaryAt);
        // The summary paragraph closes before the problem opens, and only one polite region exists.
        expect(pageSource.slice(summaryAt, problemAt)).toContain('</p>');
        expect(pageSource.match(/aria-live=/g)).toHaveLength(1);
    });
});

describe('Settings sliders', () => {
    it('use one slider row: the value beside the label, the slider and end labels close beneath', async () => {
        const { default: sliderSource } = await import('./_primitives/SettingsSlider.svelte?raw');
        const { default: detectionSource } = await import('./DetectionSettings.svelte?raw');
        const { default: dataSource } = await import('./DataSettings.svelte?raw');
        expect(sliderSource).toMatch(/<label for=\{id\}[^>]*>\{label\}<\/label>\s*<output for=\{id\}/);
        expect(sliderSource).not.toContain('h-11');
        expect(detectionSource.match(/<SettingsSlider/g)).toHaveLength(2);
        expect(detectionSource).not.toContain('type="range"');
        expect(dataSource).toContain('<SettingsSlider');
        expect(dataSource).not.toContain('type="range"');
    });
});
