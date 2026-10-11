import { beforeAll, describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import { addMessages, init } from 'svelte-i18n';
import ClassificationImageSourceSetting from './ClassificationImageSourceSetting.svelte';
import SettingsSelect from './_primitives/SettingsSelect.svelte';
import componentSource from './ClassificationImageSourceSetting.svelte?raw';
import connectionSettingsSource from './ConnectionSettings.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';
import settingsApiSource from '../../api/settings.ts?raw';
import type { ClassificationImageSource } from '../../api/settings';
import de from '../../i18n/locales/de.json';
import en from '../../i18n/locales/en.json';
import es from '../../i18n/locales/es.json';
import fr from '../../i18n/locales/fr.json';
import itLocale from '../../i18n/locales/it.json';
import ja from '../../i18n/locales/ja.json';
import pt from '../../i18n/locales/pt.json';
import ru from '../../i18n/locales/ru.json';
import zh from '../../i18n/locales/zh.json';

const OPTION_ORDER = ['frigate_snapshot', 'recording_snapshot'] as const satisfies readonly ClassificationImageSource[];
const OPTIONS_COVER_CONTRACT: [Exclude<ClassificationImageSource, (typeof OPTION_ORDER)[number]>] extends [never] ? true : false = true;

const DESCRIPTION_ID = 'classification-image-source-desc';
const RECORDING_NOTE_ID = 'classification-image-source-recording-note';
const strings = en.settings.frigate;

function renderSetting(value?: ClassificationImageSource): string {
    return render(ClassificationImageSourceSetting, { props: value ? { value } : {} }).body;
}

function selectTag(body: string): string {
    const tag = body.match(/<select\b[^>]*>/)?.[0];
    expect(tag, 'the setting renders a native select').toBeDefined();
    return tag ?? '';
}

function attribute(tag: string, name: string): string | null {
    return tag.match(new RegExp(`\\s${name}="([^"]*)"`))?.[1] ?? null;
}

function optionTags(body: string): string[] {
    return [...body.matchAll(/<option\b[^>]*>/g)].map((match) => match[0]);
}

function selectedValue(body: string): string | null {
    const selected = optionTags(body).filter((tag) => /\sselected(?:[\s=>])/.test(tag));
    expect(selected, 'exactly one option is selected').toHaveLength(1);
    return attribute(selected[0], 'value');
}

beforeAll(() => {
    addMessages('en', en);
    init({ fallbackLocale: 'en', initialLocale: 'en' });
});

describe('initial classification image setting', () => {
    it('offers exactly the generated contract values with the snapshot first', () => {
        expect(OPTIONS_COVER_CONTRACT).toBe(true);
        expect(optionTags(renderSetting()).map((tag) => attribute(tag, 'value'))).toEqual([...OPTION_ORDER]);
    });

    it('defaults to the detection snapshot when no value is supplied', () => {
        expect(selectedValue(renderSetting())).toBe('frigate_snapshot');
    });

    it('labels the select and links it to the always-visible description', () => {
        const body = renderSetting('frigate_snapshot');
        const select = selectTag(body);

        expect(attribute(select, 'id')).toBe('classification-image-source');
        expect(attribute(select, 'aria-label')).toBe(strings.classification_image_source);
        expect(attribute(select, 'aria-describedby')).toBe(DESCRIPTION_ID);
        expect(body).toContain(`id="${DESCRIPTION_ID}"`);
        expect(body).toContain(strings.classification_image_source_desc);
    });

    it('keeps the recording cost, fallback and scope out of the default form', () => {
        const body = renderSetting('frigate_snapshot');

        expect(body).not.toContain('data-recording-frame-note');
        expect(body).not.toContain(RECORDING_NOTE_ID);
        expect(body).not.toContain(strings.classification_image_recording_cost);
        expect(body).not.toContain(strings.classification_image_recording_fallback);
        expect(body).not.toContain(strings.classification_image_recording_scope);
    });

    it('states the cost, fallback and scope once the recording frame is chosen', () => {
        const body = renderSetting('recording_snapshot');
        const select = selectTag(body);

        expect(selectedValue(body)).toBe('recording_snapshot');
        expect(attribute(select, 'aria-describedby')?.split(' ')).toEqual([DESCRIPTION_ID, RECORDING_NOTE_ID]);
        expect(body).toContain(`id="${RECORDING_NOTE_ID}"`);
        expect(body).toContain(strings.classification_image_recording_cost);
        expect(body).toContain(strings.classification_image_recording_fallback.replace('{setting}', 'snapshots.clean_copy'));
        expect(body).toContain(strings.classification_image_recording_scope);
    });

    it('never disables the choice behind clip or full-visit capability', () => {
        for (const value of OPTION_ORDER) {
            const body = renderSetting(value);
            expect(attribute(selectTag(body), 'disabled')).toBeNull();
            expect(optionTags(body).some((tag) => /\sdisabled/.test(tag))).toBe(false);
        }
        expect(componentSource).not.toMatch(/recordingClip|clipsEnabled|capability/i);
    });
});

describe('settings select touch target', () => {
    function renderSelect(disabled: boolean): string {
        return render(SettingsSelect, {
            props: { id: 'probe', value: 'a', options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }], disabled, onchange: () => {} }
        }).body;
    }

    it('draws its own 44px box because native WebKit menu lists ignore padding and height', () => {
        const classes = attribute(selectTag(renderSelect(false)), 'class')?.split(/\s+/) ?? [];

        expect(classes).toEqual(expect.arrayContaining(['appearance-none', 'min-h-11', 'py-3', 'peer']));
    });

    it('keeps a visible value at 320px with enlarged text by tightening padding below sm', () => {
        const body = renderSelect(false);
        const classes = attribute(selectTag(body), 'class')?.split(/\s+/) ?? [];
        const chevronClasses = attribute(body.match(/<svg\b[^>]*>/)?.[0] ?? '', 'class')?.split(/\s+/) ?? [];

        expect(classes).toEqual(expect.arrayContaining(['pl-2', 'pr-5', 'sm:pl-4', 'sm:pr-8']));
        expect(classes).not.toContain('pl-4');
        expect(classes).not.toContain('pr-8');
        expect(chevronClasses).toEqual(expect.arrayContaining(['right-1.5', 'sm:right-3', 'w-3']));
    });

    it('keeps a native select and a decorative chevron that never intercepts the pointer', () => {
        const body = renderSelect(true);
        const chevron = body.match(/<svg\b[^>]*>/)?.[0] ?? '';

        expect(optionTags(body)).toHaveLength(2);
        expect(attribute(selectTag(body), 'disabled')).not.toBeNull();
        expect(attribute(chevron, 'aria-hidden')).toBe('true');
        expect(attribute(chevron, 'class')?.split(/\s+/)).toEqual(
            expect.arrayContaining(['pointer-events-none', 'peer-disabled:opacity-50'])
        );
    });
});

describe('initial classification image wiring', () => {
    it('types the setting from the generated contract instead of a hand-written union', () => {
        expect(settingsApiSource).toContain(
            "export type ClassificationImageSource = NonNullable<components['schemas']['SettingsResponse']['classification_image_source']>;"
        );
        expect(settingsApiSource).toContain('classification_image_source?: ClassificationImageSource;');
        expect(settingsApiSource).not.toMatch(/'frigate_snapshot'\s*\|\s*'recording_snapshot'/);
    });

    it('keeps the owner-only setting out of the guest settings payload', () => {
        const publicSettings = settingsApiSource.slice(settingsApiSource.indexOf('export interface PublicSettings'));
        const publicSettingsBody = publicSettings.slice(0, publicSettings.indexOf('}'));

        expect(publicSettingsBody).toContain('clips_enabled');
        expect(publicSettingsBody).not.toContain('classification_image_source');
    });

    it('hydrates, tracks, saves and binds the same value with the same default', () => {
        expect(settingsPageSource).toContain("let classificationImageSource = $state<ClassificationImageSource>('frigate_snapshot');");
        expect(settingsPageSource).toContain("classificationImageSource = settings.classification_image_source ?? 'frigate_snapshot';");
        expect(settingsPageSource).toContain(
            "{ key: 'classificationImageSource', val: classificationImageSource, store: s.classification_image_source ?? 'frigate_snapshot' }"
        );
        expect(settingsPageSource).toContain('classification_image_source: classificationImageSource,');
        expect(settingsPageSource).toContain('bind:classificationImageSource');

        expect(connectionSettingsSource).toContain("classificationImageSource = $bindable<ClassificationImageSource>('frigate_snapshot')");
        expect(connectionSettingsSource).toContain('<ClassificationImageSourceSetting bind:value={classificationImageSource} />');
    });

    it('sits in the basic Frigate card beside clip fetching, not behind the full-visit disclosure', () => {
        const settingIndex = connectionSettingsSource.indexOf('<ClassificationImageSourceSetting');
        const clipsIndex = connectionSettingsSource.indexOf('labelId="setting-clips-enabled"');
        const fullVisitIndex = connectionSettingsSource.indexOf('id="connection-full-visit"');

        expect(settingIndex).toBeGreaterThan(-1);
        expect(settingIndex).toBeLessThan(clipsIndex);
        expect(settingIndex).toBeLessThan(fullVisitIndex);
    });
});

describe('initial classification image copy', () => {
    const KEYS = [
        'classification_image_source',
        'classification_image_source_desc',
        'classification_image_snapshot',
        'classification_image_recording',
        'classification_image_recording_cost',
        'classification_image_recording_fallback',
        'classification_image_recording_scope'
    ] as const;
    const LOCALES = { en, de, es, fr, it: itLocale, ja, pt, ru, zh };

    for (const [name, locale] of Object.entries(LOCALES)) {
        it(`${name} carries every string without em dashes`, () => {
            const frigate = locale.settings.frigate as Record<string, unknown>;
            for (const key of KEYS) {
                const value = frigate[key];
                expect(typeof value, `${name}.${key}`).toBe('string');
                expect(String(value).trim().length, `${name}.${key}`).toBeGreaterThan(0);
                expect(String(value), `${name}.${key} uses an em dash`).not.toContain('—');
            }
        });
    }

    it('keeps the inline fallbacks in step with English', () => {
        for (const key of KEYS) {
            expect(componentSource, key).toContain(`{ default: '${strings[key]}'`);
        }
        expect(strings.classification_image_recording_fallback).toContain('30 seconds');
    });

    it('states that the recording frame needs retained recordings and the clean snapshot copy', () => {
        const fallback = strings.classification_image_recording_fallback;

        expect(fallback).toContain('retained recordings');
        expect(fallback).toContain('clean snapshot copy');
        expect(fallback).toContain('10 to 15 seconds later');
        expect(fallback).toContain('within 30 seconds');
        expect(componentSource).toContain("const CLEAN_COPY_SETTING = 'snapshots.clean_copy';");
        expect(componentSource).toContain('values: { setting: CLEAN_COPY_SETTING }');
    });

    it('wraps long setting names in the recording note instead of clipping them', () => {
        const note = renderSetting('recording_snapshot').match(/<div\b[^>]*data-recording-frame-note[^>]*>/)?.[0] ?? '';

        expect(attribute(note, 'class')?.split(/\s+/)).toContain('break-words');
    });

    // A live detection waits until its recording frame is written, and gives up after 30 seconds.
    const DEADLINE: Record<keyof typeof LOCALES, string> = {
        en: '30 seconds',
        de: '30 Sekunden',
        es: '30 segundos',
        fr: '30 secondes',
        it: '30 secondi',
        ja: '30 秒',
        pt: '30 segundos',
        ru: '30 секунд',
        zh: '30 秒'
    };

    for (const [name, locale] of Object.entries(LOCALES) as Array<[keyof typeof LOCALES, typeof en]>) {
        it(`${name} names the clean copy requirement and the 30-second deadline`, () => {
            const fallback = String((locale.settings.frigate as Record<string, unknown>).classification_image_recording_fallback);

            expect(fallback, `${name} fallback names the Frigate setting through a placeholder`).toContain('({setting})');
            expect(fallback, `${name} fallback must not translate the setting name`).not.toContain('clean_copy');
            expect(fallback, `${name} fallback names the deadline`).toContain(DEADLINE[name]);
        });
    }
});
