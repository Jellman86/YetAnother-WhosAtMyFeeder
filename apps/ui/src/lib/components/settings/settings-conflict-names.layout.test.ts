import { beforeAll, describe, expect, it } from 'vitest';
import { createRawSnippet } from 'svelte';
import { render } from 'svelte/server';
import { addMessages, init } from 'svelte-i18n';
import SettingsPage from './_primitives/SettingsPage.svelte';
import enSettings from '../../i18n/locales/en/settings.json';
import deSettings from '../../i18n/locales/de/settings.json';
import esSettings from '../../i18n/locales/es/settings.json';
import frSettings from '../../i18n/locales/fr/settings.json';
import itSettings from '../../i18n/locales/it/settings.json';
import jaSettings from '../../i18n/locales/ja/settings.json';
import ptSettings from '../../i18n/locales/pt/settings.json';
import ruSettings from '../../i18n/locales/ru/settings.json';
import zhSettings from '../../i18n/locales/zh/settings.json';

// Each conflict row has the same two buttons. Moving between buttons with a screen reader must
// still say which setting each one decides, and the name must begin with the words on screen
// (WCAG 2.5.3), so speech users can say what they see.

const conflicts = [
    { field: 'mqtt_server', label: 'MQTT broker (Connection)' },
    { field: 'mqtt_port', label: 'Port (Connection)' }
];

function renderConflicts(): string {
    return render(SettingsPage, {
        props: {
            title: 'Settings',
            conflicts,
            restoredNotice: "You left with unsaved changes. They're still here.",
            children: createRawSnippet(() => ({ render: () => '<div></div>' }))
        }
    }).body;
}

// The accessible name of each conflict button: its visible words followed by its visually hidden
// text. Read directly from the two parts rather than by stripping markup.
function buttonNames(body: string): string[] {
    return [...body.matchAll(/<button\b[^>]*>([^<]*)(?:<!---->)*<span class="sr-only">([^<]*)<\/span>/g)]
        .map((match) => `${match[1]}${match[2]}`.replace(/\s+/g, ' ').trim());
}

beforeAll(() => {
    addMessages('en', { settings: enSettings });
    init({ fallbackLocale: 'en', initialLocale: 'en' });
});

describe('the buttons that settle a conflict', () => {
    it('name the setting each one decides, starting with the words on screen', () => {
        const names = buttonNames(renderConflicts());
        expect(names).toContain('Use the saved value for MQTT broker (Connection)');
        expect(names).toContain('Use my change for MQTT broker (Connection)');
        expect(names).toContain('Use the saved value for Port (Connection)');
        expect(names).toContain('Use my change for Port (Connection)');
        // Four buttons, and no two of them sound the same.
        expect(names).toHaveLength(4);
        expect(new Set(names).size).toBe(names.length);
    });

    it('add the setting in every language, after the visible words', () => {
        const locales = { de: deSettings, en: enSettings, es: esSettings, fr: frSettings, it: itSettings, ja: jaSettings, pt: ptSettings, ru: ruSettings, zh: zhSettings };
        for (const [locale, messages] of Object.entries(locales)) {
            const suffix = (messages.save_bar as Record<string, string>).conflict_choice_for;
            expect(suffix, `${locale} names the setting`).toContain('{field}');
            expect(suffix.trim().startsWith('{field}'), `${locale} keeps the visible words first`).toBe(false);
        }
    });
});
