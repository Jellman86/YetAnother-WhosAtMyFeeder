import { describe, expect, it } from 'vitest';
import { authoredLocale } from '../i18n/authored-locales';
import { SETTINGS_PART_ORDER, SETTINGS_SECTION_ORDER } from './settings-route';
import { settingsGroupPlace, settingsPartPlace, settingsSectionName, settingsSectionPlace } from './settings-place';

const LANGUAGES = ['en', 'de', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'zh'] as const;

function translator(language: string): (key: string) => string {
    const dictionary = authoredLocale(language) as Record<string, unknown>;
    return (key) => {
        const value = key.split('.').reduce<unknown>((node, name) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[name] : undefined), dictionary);
        if (typeof value !== 'string') throw new Error(`Missing locale key ${key} in ${language}`);
        return value;
    };
}

describe('a place in Settings, named from the navigation labels', () => {
    it('names the feeder location where the route puts it', () => {
        const t = translator('en');
        expect(settingsPartPlace('location', t)).toBe('Settings → Cameras & connection → Location');
        expect(settingsPartPlace('birdnet', t)).toBe('Settings → Integrations → BirdNET-Go');
        expect(settingsSectionPlace('access', t)).toBe('Settings → Access & privacy');
        expect(settingsSectionName('notifications', t)).toBe('Notifications');
        expect(settingsGroupPlace('identification', 'settings.detection.hardware_title', t)).toBe('Settings → Identifying birds → Hardware');
    });

    it.each(LANGUAGES)('%s has a name for every section and every part', (language) => {
        const t = translator(language);
        for (const section of SETTINGS_SECTION_ORDER) expect(settingsSectionPlace(section, t)).not.toBe('');
        for (const part of SETTINGS_PART_ORDER) expect(settingsPartPlace(part, t)).not.toBe('');
    });
});
