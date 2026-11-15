import { describe, expect, it } from 'vitest';
import { SETTINGS_TAB_ORDER } from '../settings/settings-route';
import { authoredLocale } from './authored-locales';

const LANGUAGES = ['en', 'de', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'zh'] as const;

interface Pointer {
    key: string;
    target: string;
}

function strings(node: unknown, path: string): Array<[string, string]> {
    if (typeof node === 'string') return [[path, node]];
    if (!node || typeof node !== 'object') return [];
    return Object.entries(node).flatMap(([key, value]) => strings(value, path ? `${path}.${key}` : key));
}

function text(dictionary: unknown, path: string): string {
    const found = strings(dictionary, '').find(([key]) => key === path);
    if (!found) throw new Error(`Missing locale key ${path}`);
    return found[1];
}

/** Every "Settings → …" in a language's copy, with the words that follow the arrow. */
function settingsPointers(language: string): Pointer[] {
    const dictionary = authoredLocale(language);
    const settingsWord = text(dictionary, 'nav.settings');
    return strings(dictionary, '').flatMap(([key, value]) => {
        const pointers: Pointer[] = [];
        let from = value.indexOf(settingsWord);
        while (from !== -1) {
            const after = value.slice(from + settingsWord.length);
            const arrow = /^\s*(?:→|->)\s*(?=\S)/.exec(after);
            if (arrow) pointers.push({ key, target: after.slice(arrow[0].length) });
            from = value.indexOf(settingsWord, from + settingsWord.length);
        }
        return pointers;
    });
}

/** What the Settings navigation offers: its tabs, and the button that reopens the setup wizard. */
function settingsDestinations(language: string): string[] {
    const dictionary = authoredLocale(language);
    return [...SETTINGS_TAB_ORDER.map((tab) => text(dictionary, `settings.tabs.${tab}`)), text(dictionary, 'nav.setup_wizard')];
}

describe('"Settings → …" pointers in copy', () => {
    it.each(LANGUAGES)('%s names a real Settings tab after every arrow', (language) => {
        const destinations = settingsDestinations(language);
        const stale = settingsPointers(language).filter(
            ({ target }) => !destinations.some((destination) => target.startsWith(destination))
        );
        expect(stale).toEqual([]);
    });

    it('finds the pointers it is meant to guard', () => {
        expect(settingsPointers('en').length).toBeGreaterThan(20);
        for (const language of LANGUAGES) expect(settingsPointers(language).length).toBeGreaterThan(10);
    });

    it.each(LANGUAGES)('%s sends each setting to the tab that holds it', (language) => {
        const dictionary = authoredLocale(language);
        const settingsWord = text(dictionary, 'nav.settings');
        const tab = (id: string): string => text(dictionary, `settings.tabs.${id}`);
        // Location, and the country read from it, is a card on Integrations; importing missed
        // detections is a Maintenance job.
        expect(text(dictionary, 'garden.country_missing')).toContain(`${settingsWord} → ${tab('integrations')}`);
        expect(text(dictionary, 'garden.automatic_location_required')).toContain(`${settingsWord} → ${tab('integrations')}`);
        expect(text(dictionary, 'events.empty_desc')).toContain(`${settingsWord} → ${tab('maintenance')}`);
    });

    it.each(LANGUAGES)('%s never calls Health a Settings tab', (language) => {
        const dictionary = authoredLocale(language);
        expect(text(dictionary, 'settings.data.diagnostics_desc')).toContain(text(dictionary, 'nav.health'));
    });
});
