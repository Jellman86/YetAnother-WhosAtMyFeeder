import { describe, expect, it } from 'vitest';
import { settingsFieldSection } from '../../settings/settings-fields';
import settingsPageSource from '../../pages/Settings.svelte?raw';
import integrationSource from './IntegrationSettings.svelte?raw';
import aiSource from './AISettings.svelte?raw';

describe('the Settings save model', () => {
    it('gives every field the draft tracks a section, so the save bar can name where each change is', () => {
        const tracked = [...settingsPageSource.matchAll(/\{\s*field: '(\w+)', draft:/g)].map((match) => match[1]);
        expect(tracked.length).toBeGreaterThan(150);
        expect(tracked.filter((field) => settingsFieldSection(field) === null)).toEqual([]);
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
        expect(problemAt).toBeGreaterThan(-1);
        // The problem is in the save details and the running count in the bar: two sections, neither
        // inside the other, and only one polite region.
        expect(problemAt).toBeLessThan(pageSource.indexOf('data-settings-save-bar'));
        expect(pageSource.slice(problemAt, summaryAt)).toContain('</section>');
        expect(pageSource.match(/aria-live=/g)).toHaveLength(1);
    });
});

describe('stored-secret flags', () => {
    it('are never reset by an effect: whether a secret is stored follows from the saved copy alone', async () => {
        const { default: integrationsSource } = await import('./IntegrationSettings.svelte?raw');
        // An effect that cleared "saved" once anything was typed made a field cleared again look
        // empty, although saving an empty field keeps the stored secret.
        const resetting = /\$effect\(\(\) => \{[^}]*Saved = false/;
        expect(settingsPageSource).not.toMatch(resetting);
        expect(integrationsSource).not.toMatch(resetting);
    });
});

describe('Settings sliders', () => {
    it('use one slider row: the value beside the label, the slider and end labels close beneath', async () => {
        const { default: sliderSource } = await import('./_primitives/SettingsSlider.svelte?raw');
        const { default: detectionSource } = await import('./NamingSettings.svelte?raw');
        const { default: dataSource } = await import('./DataSettings.svelte?raw');
        // The value sits beside the label for the eye only: the focused slider announces it once,
        // through aria-valuetext. An <output> is a live region and would announce it again.
        // The value is plain text at the right of the control column, not a coloured pill.
        // Regular weight in the ink colour: the label is the one semibold thing in a row.
        expect(sliderSource).toMatch(/<p class="text-right text-sm tabular-nums text-ink" aria-hidden="true">\{shown\}<\/p>/);
        expect(sliderSource).not.toContain('bg-brand-700');
        expect(sliderSource).not.toContain('<output');
        expect(sliderSource).toContain('aria-valuetext={shown}');
        expect(sliderSource).not.toContain('h-11');
        // The birds' threshold and floor, and Garden's naming threshold while the beta is on.
        expect(detectionSource.match(/<SettingsSlider/g)).toHaveLength(3);
        expect(detectionSource).not.toContain('type="range"');
        expect(dataSource).toContain('<SettingsSlider');
        expect(dataSource).not.toContain('type="range"');
    });
});
