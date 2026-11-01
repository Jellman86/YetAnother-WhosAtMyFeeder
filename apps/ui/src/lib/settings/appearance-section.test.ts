import { describe, expect, it, vi } from 'vitest';
import type { Settings } from '../api/settings';

vi.mock('../stores/settings.svelte', () => ({ settingsStore: { settings: null } }));
vi.mock('../stores/auth.svelte', () => ({ authStore: {} }));

const { appearanceSection } = await import('./appearance-section');
const { sectionIsDirty } = await import('./section-adapter');

function saved(fields: Partial<Settings>): Settings {
    return fields as Settings;
}

describe('Appearance section draft', () => {
    it('loads the saved choices, with the defaults for anything a server leaves out', () => {
        expect(appearanceSection.decode(saved({}))).toEqual({
            displayCommonNames: true,
            scientificNamePrimary: false,
            explorerView: 'cards',
            dateFormat: 'locale',
            timeFormat: 'locale',
            fontTheme: 'classic',
            colorTheme: 'bluetit'
        });
        expect(
            appearanceSection.decode(
                saved({
                    display_common_names: false,
                    scientific_name_primary: true,
                    appearance_explorer_view: 'list',
                    date_format: 'ymd',
                    time_format: '24h',
                    appearance_font_theme: 'studio',
                    appearance_color_theme: 'default'
                })
            )
        ).toEqual({
            displayCommonNames: false,
            scientificNamePrimary: true,
            explorerView: 'list',
            dateFormat: 'ymd',
            timeFormat: '24h',
            fontTheme: 'studio',
            colorTheme: 'default'
        });
    });

    it('reads unknown saved values as the same defaults the form shows', () => {
        const draft = appearanceSection.decode(
            saved({ date_format: 'weekday', time_format: 'sundial', appearance_font_theme: 'comic', appearance_color_theme: 'neon' })
        );
        expect(draft).toMatchObject({ dateFormat: 'locale', timeFormat: 'locale', fontTheme: 'classic', colorTheme: 'bluetit' });
    });

    it('sends every Appearance field, so an unchanged section still saves what is shown', () => {
        const draft = appearanceSection.decode(saved({ date_format: 'dmy', appearance_font_theme: 'clean' }));
        expect(appearanceSection.encodePatch(draft)).toEqual({
            display_common_names: true,
            scientific_name_primary: false,
            appearance_explorer_view: 'cards',
            date_format: 'dmy',
            time_format: 'locale',
            appearance_font_theme: 'clean',
            appearance_color_theme: 'bluetit'
        });
    });

    it('is unsaved only after a choice changes', () => {
        const stored = saved({ date_format: 'dmy', appearance_color_theme: 'default' });
        const draft = appearanceSection.decode(stored);
        expect(sectionIsDirty(appearanceSection, draft, stored)).toBe(false);
        expect(sectionIsDirty(appearanceSection, { ...draft, timeFormat: '12h' }, stored)).toBe(true);
        expect(sectionIsDirty(appearanceSection, { ...draft, colorTheme: 'bluetit' }, stored)).toBe(true);
        expect(sectionIsDirty(appearanceSection, { ...draft, explorerView: 'list' }, stored)).toBe(true);
    });

    it('does not count a saved value the form normalises as an edit', () => {
        // A legacy or unknown saved value loads as the default; leaving it alone is not a change.
        const stored = saved({ date_format: 'weekday', appearance_font_theme: undefined });
        expect(sectionIsDirty(appearanceSection, appearanceSection.decode(stored), stored)).toBe(false);
    });
});
