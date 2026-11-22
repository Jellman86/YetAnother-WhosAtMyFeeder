import { describe, expect, it } from 'vitest';
import { SETTINGS_SECTION_ORDER } from '../settings/settings-route';
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

/** What the Settings navigation offers: its sections, and the button that reopens the setup wizard. */
function settingsDestinations(language: string): string[] {
    const dictionary = authoredLocale(language);
    return [...SETTINGS_SECTION_ORDER.map((section) => text(dictionary, `settings.sections.${section}`)), text(dictionary, 'nav.setup_wizard')];
}

describe('"Settings → …" pointers in copy', () => {
    it.each(LANGUAGES)('%s names a real Settings section after every arrow', (language) => {
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

    it.each(LANGUAGES)('%s sends each setting to the section that holds it', (language) => {
        const dictionary = authoredLocale(language);
        const settingsWord = text(dictionary, 'nav.settings');
        const section = (id: string): string => text(dictionary, `settings.sections.${id}`);
        // Importing missed detections is a job in Storage & upkeep; the AI key is an integration;
        // sign-in is in Access & privacy; the channels are in Notifications.
        expect(text(dictionary, 'events.empty_desc')).toContain(`${settingsWord} → ${section('storage')}`);
        expect(text(dictionary, 'detection.ai.conversation_error')).toContain(`${settingsWord} → ${section('integrations')}`);
        expect(text(dictionary, 'setup.account.already')).toContain(`${settingsWord} → ${section('access')}`);
        expect(text(dictionary, 'setup.integrations.notifications_note')).toContain(`${settingsWord} → ${section('notifications')}`);
    });

    it.each(LANGUAGES)('%s leaves a place that has moved before to the navigation labels', (language) => {
        const dictionary = authoredLocale(language);
        // These name the feeder location, BirdNET-Go and Hardware, which have each moved section. The
        // sentence holds a slot; settings-place.ts fills it from the section and part labels.
        for (const key of ['garden.country_missing', 'garden.automatic_location_required', 'setup.model.location_hint', 'settings.detection.model_manager_location_desc', 'events.heard.none_stored', 'settings.beta.garden_device_note', 'settings.models.status_missing_next_about']) {
            expect(text(dictionary, key), key).toContain('{place}');
        }
        for (const key of ['settings.beta.garden_country_missing', 'settings.beta.garden_alerts_elsewhere', 'settings.range_filter.status_needs_location_detail', 'settings.frigate.stage_frigate_next', 'settings.frigate.stage_mqtt_next', 'settings.notifications.garden_off', 'settings.integrations.elsewhere_pipeline']) {
            expect(text(dictionary, key), key).toContain('{section}');
        }
    });

    // What Sharing & integrations was called in each language. It was split into Integrations and
    // Access & privacy, so no sentence may still name it.
    const RETIRED_SECTION_NAMES: Readonly<Record<(typeof LANGUAGES)[number], string>> = {
        en: 'Sharing & integrations',
        de: 'Teilen & Integrationen',
        es: 'Compartir e integraciones',
        fr: 'Partage et intégrations',
        it: 'Condivisione e integrazioni',
        ja: '共有と統合',
        pt: 'Compartilhamento e integrações',
        ru: 'Обмен и интеграции',
        zh: '共享与集成'
    };

    it.each(LANGUAGES)('%s names no section that Settings no longer has', (language) => {
        const dictionary = authoredLocale(language);
        const retired = RETIRED_SECTION_NAMES[language];
        expect(strings(dictionary, '').filter(([, value]) => value.includes(retired)).map(([key]) => key)).toEqual([]);
        // The older pointer style, "Settings › Models", named tabs that are parts now.
        const settingsWord = text(dictionary, 'nav.settings');
        expect(strings(dictionary, '').filter(([, value]) => value.includes(`${settingsWord} ›`)).map(([key]) => key)).toEqual([]);
    });

    it.each(LANGUAGES)('%s no longer points at a tab Settings no longer has', (language) => {
        const dictionary = authoredLocale(language);
        const settingsWord = text(dictionary, 'nav.settings');
        const sectionNames = SETTINGS_SECTION_ORDER.map((id) => text(dictionary, `settings.sections.${id}`));
        const formerTabs = ['connection', 'detection', 'models', 'beta', 'notifications', 'integrations', 'ai', 'security', 'data', 'maintenance', 'appearance', 'accessibility']
            .map((id) => text(dictionary, `settings.tabs.${id}`))
            // A section may share a former tab's name, as German Alerts shares Notifications'.
            .filter((name) => !sectionNames.includes(name));
        const stale = settingsPointers(language).filter(({ target }) => formerTabs.some((name) => target.startsWith(name)));
        expect(stale).toEqual([]);
    });
});
