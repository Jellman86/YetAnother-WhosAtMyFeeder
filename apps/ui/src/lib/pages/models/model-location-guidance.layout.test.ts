import { describe, expect, it } from 'vitest';

import modelManagerSource from './ModelManager.svelte?raw';
import modelSettingsSource from '../../components/settings/ModelSettings.svelte?raw';
import settingsSource from '../Settings.svelte?raw';
import enSettings from '../../i18n/locales/en/settings.json';

const en = { settings: enSettings };

describe('Model Manager location guidance', () => {
    it('gates the guidance on the declared metadata contract, not a model id', () => {
        expect(modelManagerSource).toContain("import { usesSavedFeederLocation } from './model_location_input'");
        expect(modelManagerSource).toContain('{#if usesSavedFeederLocation(model)}');
        expect(modelManagerSource).not.toMatch(/model\.id\s*===\s*['"][^'"]*location/i);
    });

    it('explains the location behaviour in localized plain language', () => {
        expect(modelManagerSource).toContain('settings.detection.model_manager_location_title');
        expect(modelManagerSource).toContain('settings.detection.model_manager_location_desc');
        const desc = en.settings.detection.model_manager_location_desc;
        // The place is filled in from the navigation's own labels, so it follows the section map.
        expect(desc).toContain('{place}');
        expect(modelManagerSource).toContain("values: { place: settingsPartPlace('location', $_) }");
        expect(desc).toMatch(/without location/i);
        expect(desc).toMatch(/date/i);
        expect(desc).toMatch(/uncertainty|accuracy radius/i);
        expect(desc).not.toMatch(/inat2021|metadata|tensor|worker/i);
    });

    it('never shows or fetches the saved coordinates', () => {
        expect(modelManagerSource).not.toMatch(/latitude|longitude/);
        expect(modelManagerSource).not.toContain('fetchSettings');
    });

    it('links to the real Location settings tab without a full reload', () => {
        // A new tab lands on the location's own part of Cameras & connection.
        expect(modelManagerSource).toContain("href={toAppPath(settingsPartPath('location'))}");
        expect(modelManagerSource).toContain('settings.detection.model_manager_location_link');
        // Plain left clicks stay in the app so unsaved settings edits survive;
        // modified clicks fall through to the browser (new tab, etc.).
        expect(modelManagerSource).toContain('event.metaKey');
        expect(modelManagerSource).toContain('onopenlocationsettings();');
        expect(modelSettingsSource).toMatch(/<ModelManager[^>]*\{onopenlocationsettings\}\s*\/>/);
        // Both the model guidance and the range filter land on the location field itself.
        expect(settingsSource).toContain('onopenlocationsettings={() => void openLocationField()}');
        expect(settingsSource).toContain("openFieldInPart('location', '#location-lat'");
    });
});

describe('Model Manager incomplete-install wording', () => {
    it('does not blame missing label files, which catalogue models never have', () => {
        const repair = en.settings.detection.model_manager_repair_needed;
        expect(repair).not.toMatch(/labels/i);
        expect(repair).toMatch(/species names/i);
        expect(repair).toMatch(/model configuration/i);
        expect(modelManagerSource).not.toContain('missing labels or configuration');
    });
});
