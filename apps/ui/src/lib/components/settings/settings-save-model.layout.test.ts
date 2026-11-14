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
