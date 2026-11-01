import { describe, expect, it } from 'vitest';
import appearanceSettingsSource from './AppearanceSettings.svelte?raw';
import enSettings from '../../i18n/locales/en/settings.json';

const enLocale = { settings: enSettings };

describe('time format control', () => {
    it('sits beside the date format control in Appearance', () => {
        expect(appearanceSettingsSource).toContain('id="time-format-select"');
        expect(appearanceSettingsSource).toContain('labelId="setting-time-format"');
        expect(appearanceSettingsSource.indexOf('date-format-select')).toBeLessThan(
            appearanceSettingsSource.indexOf('time-format-select')
        );
    });

    it('offers exactly the three formats the API accepts', () => {
        for (const value of ["value: 'locale'", "value: '12h'", "value: '24h'"]) {
            expect(appearanceSettingsSource).toContain(value);
        }
    });

    it('is labelled for assistive technology, not left to the placeholder', () => {
        expect(appearanceSettingsSource).toContain("ariaLabel={$_('settings.time_format.label')}");
    });

    it('stops claiming the date control also sets the time', () => {
        expect(enLocale.settings.date_format.desc).not.toMatch(/time/i);
        expect(enLocale.settings.time_format.label).toBeTruthy();
    });
});


describe('browser date preference', () => {
    it('offers the saved browser-language date value as a labelled option', () => {
        const dateControl = appearanceSettingsSource.split('id="date-format-select"')[1].split('id="time-format-select"')[0];
        expect(dateControl).toContain("value: 'locale'");
        expect(dateControl).toContain("settings.date_format.locale");
        expect(enLocale.settings.date_format).toHaveProperty('locale');
    });
});
