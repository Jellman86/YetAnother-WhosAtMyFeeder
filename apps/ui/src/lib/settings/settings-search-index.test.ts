// @ts-nocheck: this source audit runs under Vitest's Node environment; Node types are
// intentionally absent from the browser application tsconfig.
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { authoredLocale } from '../i18n/authored-locales';
import { SETTINGS_SECTION_ORDER } from './settings-route';
import { settingsMoreId } from './settings-more';
import { SETTINGS_SEARCH_INDEX, settingsSearchEntry } from './settings-search-index';
import { readSettingsMarkup, settingsComponentFiles, SETTINGS_COMPONENTS_DIR } from './settings-markup.test-support';

/**
 * The search index against the markup it describes, in every component under Settings, subfolders
 * included. What fails here:
 * - a `SettingsRow`, `SettingsSlider` or `SettingsCard` with no static id or no entry, or an entry
 *   whose label, help, anchor or disclosure no longer matches it;
 * - a row built in a loop that is not declared below with the entries it makes;
 * - a control (a kit control or a bare input, select or textarea) outside any row or card header,
 *   unless its file is declared below with the entries that find it.
 * What it cannot see: a setting drawn with none of those, such as a custom element with a click
 * handler. The browser suite then proves each entry lands where it says.
 */
const COMPONENTS_DIR = SETTINGS_COMPONENTS_DIR;
const LANGUAGES = ['en', 'de', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'zh'];

/**
 * Rows built in a loop, whose anchors and labels are not literals: how many such rows the file has,
 * the prefix their ids take, how the loop's items are written, and the entry each item gets.
 */
const LOOPED_ROWS: Record<string, { rows: number; prefix: string; items: RegExp; anchors: string[] }> = {
    'AccessibilitySettings.svelte': {
        rows: 1,
        prefix: 'setting-',
        items: /^\s+id: '([^']+)',$/gm,
        anchors: ['setting-high-contrast', 'setting-dyslexia-font', 'setting-reduced-motion', 'setting-live-announcements']
    },
    'HaWeatherSettings.svelte': {
        rows: 1,
        prefix: 'setting-ha-weather-',
        items: /\{ id: '([^']+)', label: /g,
        anchors: [
            'setting-ha-weather-temperature', 'setting-ha-weather-wind-speed', 'setting-ha-weather-wind-direction', 'setting-ha-weather-cloud-cover',
            'setting-ha-weather-precipitation', 'setting-ha-weather-rain', 'setting-ha-weather-snowfall'
        ]
    }
};

/**
 * Controls that sit outside a `SettingsRow` and a card's header: how many of each the file has, why,
 * and the entries that find them. A control added to one of these files changes the count and fails,
 * so it is given an entry (or joins one) on purpose.
 */
const CONTROLS_OUTSIDE_ROWS: Record<string, { controls: Record<string, number>; why: string; foundBy: string[] }> = {
    'BetaFeatureCard.svelte': { controls: { SettingsToggle: 1 }, why: "the feature's own switch, beside its heading", foundBy: ['beta-garden-animals-name'] },
    'CameraWatchRow.svelte': { controls: { select: 2, SettingsToggle: 1 }, why: 'one row per Frigate camera, named by the camera', foundBy: ['settings-group-cameras'] },
    'ConnectionSettings.svelte': {
        controls: { SettingsInput: 2, input: 1 },
        why: "the broker's address and port share one hand-built row; the nest dedupe window belongs to the camera list",
        foundBy: ['setting-mqtt-broker', 'settings-group-cameras']
    },
    'DetectionSettings.svelte': { controls: { SettingsInput: 1 }, why: 'the species search that fills the blocked list', foundBy: ['settings-group-detection-blocked-labels'] },
    'GardenBetaSettings.svelte': { controls: { select: 1 }, why: "a choice inside one of Garden's own parts", foundBy: ['beta-garden-animals-name'] },
    'GardenNotificationSettings.svelte': { controls: { input: 1 }, why: "the channel tick boxes under Garden's alert switch", foundBy: ['garden-notifications'] },
    'HardwareSettings.svelte': { controls: { SettingsToggle: 1 }, why: 'an option of the device check, which is an action and saves nothing', foundBy: ['models-hardware'] },
    'MaintenanceSettings.svelte': { controls: { input: 2 }, why: 'the two dates of a custom import window', foundBy: ['setting-backfill-window'] },
    'NotificationChannelsSettings.svelte': {
        controls: { SettingsToggle: 7, SecretInput: 8, input: 9, select: 1 },
        why: "each channel's own fields, shown under its switch once the channel is on",
        foundBy: ['discord-channel-label', 'pushover-channel-label', 'telegram-channel-label', 'email-channel-label']
    },
    'NotificationPolicySentence.svelte': { controls: { input: 2, SettingsToggle: 1 }, why: 'the choices inside the alert sentence', foundBy: ['settings-group-notifications-global-filters'] },
    'NotificationSettings.svelte': {
        controls: { SettingsToggle: 1, input: 8, select: 1 },
        why: 'the cooldown, language, address, link and species filter, each a hand-built block with an entry of its own',
        foundBy: ['notification-cooldown-label', 'notification-language', 'notification-instance-url', 'notification-link-opens', 'notification-species-filter-section']
    }
};

const allSources = (): string =>
    [
        ...settingsComponentFiles().map((file) => join(COMPONENTS_DIR, file)),
        ...readdirSync(__dirname).filter((name) => name.endsWith('.ts') && !name.includes('.test') && !name.startsWith('settings-search-index')).map((name) => join(__dirname, name))
    ].map((path) => readFileSync(path, 'utf8')).join('\n');

function message(dictionary: unknown, key: string): unknown {
    let node = dictionary;
    for (const part of key.split('.')) node = node && typeof node === 'object' ? node[part] : undefined;
    return node;
}

describe('the settings search index', () => {
    const { rows: found, controls } = readSettingsMarkup();

    it('has an entry for every row and slider, under the label and help the row shows', () => {
        const problems: string[] = [];
        const looped: Record<string, number> = {};
        for (const row of found.filter((each) => each.tag !== 'SettingsCard')) {
            if (row.dynamic) {
                looped[row.file] = (looped[row.file] ?? 0) + 1;
                continue;
            }
            if (!row.anchor) {
                problems.push(`${row.file}: the "${row.labelKey}" row has no labelId, so the search cannot land on it`);
                continue;
            }
            const entry = settingsSearchEntry(row.anchor);
            if (!entry) problems.push(`${row.file}: ${row.anchor} ("${row.labelKey}") has no entry`);
            else if (entry.labelKey !== row.labelKey) problems.push(`${row.anchor}: the index says ${entry.labelKey}, the row shows ${row.labelKey}`);
            else if (row.helpKey && entry.helpKey !== row.helpKey) problems.push(`${row.anchor}: the index's help is ${entry.helpKey}, the row shows ${row.helpKey}`);
        }
        expect(problems).toEqual([]);
        // A row built in a loop is indexed by hand: only where declared, as many rows as declared,
        // and one entry for each item the loop holds.
        expect(looped).toEqual(Object.fromEntries(Object.entries(LOOPED_ROWS).map(([file, declared]) => [file, declared.rows])));
        for (const [file, declared] of Object.entries(LOOPED_ROWS)) {
            const source = readFileSync(join(COMPONENTS_DIR, file), 'utf8');
            const items = [...source.matchAll(declared.items)].map((match) => `${declared.prefix}${match[1]}`);
            expect(items.sort(), `${file}: one entry for each item of its loop`).toEqual([...declared.anchors].sort());
            for (const anchor of declared.anchors) expect(settingsSearchEntry(anchor), anchor).not.toBeNull();
        }
    });

    it('finds every control that sits outside a row through a declared entry', () => {
        const loose: Record<string, Record<string, number>> = {};
        for (const control of controls.filter((each) => !each.held)) {
            loose[control.file] ??= {};
            loose[control.file][control.tag] = (loose[control.file][control.tag] ?? 0) + 1;
        }
        // An exact count: a new control in one of these files, or a first one in another, fails until
        // it is in a `SettingsRow` or is declared here with the entry that finds it.
        expect(loose).toEqual(Object.fromEntries(Object.entries(CONTROLS_OUTSIDE_ROWS).map(([file, declared]) => [file, declared.controls])));
        for (const [file, declared] of Object.entries(CONTROLS_OUTSIDE_ROWS)) {
            expect(declared.why, file).not.toBe('');
            for (const anchor of declared.foundBy) expect(settingsSearchEntry(anchor), `${file}: ${anchor}`).not.toBeNull();
        }
    });

    it('reads components in subfolders, and reads rows, loops and loose controls the way it claims', () => {
        expect(settingsComponentFiles()).toContain('sections/NotificationsSection.svelte');
        const sources: Record<string, string> = {
            'garden/New.svelte': `<SettingsCard id="g" title={$_('a.title')}>
                <SettingsRow labelId="setting-new" label={$_('a.new')} description={$_('a.new_help')}><SettingsToggle /></SettingsRow>
                {#each items as item}<SettingsRow labelId="setting-{item.id}" label={item.label}><SettingsInput /></SettingsRow>{/each}
                <label>Loose <input type="text" /></label>
                <SettingsInput id="outside" />
                {#snippet actions()}<SettingsToggle />{/snippet}
            </SettingsCard>`
        };
        const read = readSettingsMarkup(Object.keys(sources), (file) => sources[file]);
        expect(read.rows.map((row) => [row.tag, row.anchor, row.labelKey, row.dynamic])).toEqual([
            ['SettingsCard', 'g', 'a.title', false],
            ['SettingsRow', 'setting-new', 'a.new', false],
            ['SettingsRow', null, null, true]
        ]);
        expect(read.controls.map((control) => [control.tag, control.held])).toEqual([
            ['SettingsToggle', true], ['SettingsInput', true], ['input', false], ['SettingsInput', false], ['SettingsToggle', true]
        ]);
    });

    it('has a group entry for every card of settings, under the card\'s title', () => {
        const problems: string[] = [];
        for (const card of found.filter((each) => each.tag === 'SettingsCard')) {
            if (!card.anchor) {
                problems.push(`${card.file}: the "${card.labelKey}" card has no id, so the search cannot land on it`);
                continue;
            }
            const entry = settingsSearchEntry(card.anchor);
            if (!entry) problems.push(`${card.file}: the ${card.anchor} card ("${card.labelKey}") has no entry`);
            else if (entry.kind !== 'group') problems.push(`${card.anchor}: a card's entry is a group`);
            else if (entry.labelKey !== card.labelKey) problems.push(`${card.anchor}: the index says ${entry.labelKey}, the card shows ${card.labelKey}`);
        }
        expect(problems).toEqual([]);
    });

    it('opens the disclosures each row sits inside', () => {
        const problems: string[] = [];
        for (const row of found) {
            const entry = row.anchor ? settingsSearchEntry(row.anchor) : null;
            if (!entry) continue;
            const missing = row.within.filter((id) => !(entry.disclosures ?? []).includes(id));
            if (missing.length > 0) problems.push(`${entry.anchor}: sits inside ${missing.join(', ')}, which its entry does not open`);
        }
        expect(problems).toEqual([]);
    });

    it('names only anchors and disclosures that are in the markup', () => {
        const sources = allSources();
        const moreIds = new Set(SETTINGS_SECTION_ORDER.map(settingsMoreId));
        const inMarkup = (id: string): boolean => {
            if (sources.includes(`"${id}"`) || sources.includes(`'${id}'`)) return true;
            // A looped row's id is checked against its loop above; a beta feature's heading is named from its id.
            if (Object.values(LOOPED_ROWS).some((declared) => declared.anchors.includes(id))) return true;
            const beta = /^beta-(.+)-name$/.exec(id);
            return Boolean(beta && sources.includes(`id="${beta[1]}"`));
        };
        const problems: string[] = [];
        for (const entry of SETTINGS_SEARCH_INDEX) {
            if (!inMarkup(entry.anchor)) problems.push(`${entry.anchor}: no element has this id`);
            for (const id of entry.disclosures ?? []) if (!moreIds.has(id) && !inMarkup(id)) problems.push(`${entry.anchor}: no disclosure is called ${id}`);
        }
        expect(problems).toEqual([]);
    });

    it('has one entry per anchor, More options first among its disclosures, and a real entry behind each', () => {
        const anchors = SETTINGS_SEARCH_INDEX.map((entry) => entry.anchor);
        expect(anchors.filter((anchor, index) => anchors.indexOf(anchor) !== index)).toEqual([]);
        const moreIds = new Set(SETTINGS_SECTION_ORDER.map(settingsMoreId));
        for (const entry of SETTINGS_SEARCH_INDEX) {
            expect((entry.disclosures ?? []).slice(1).filter((id) => moreIds.has(id)), entry.anchor).toEqual([]);
            if (entry.behind) {
                const behind = settingsSearchEntry(entry.behind);
                expect(behind, `${entry.anchor} is behind ${entry.behind}`).not.toBeNull();
                expect(behind?.behind ? settingsSearchEntry(behind.behind)?.behind : undefined, `${entry.anchor}: at most two steps behind`).toBeUndefined();
            }
            for (const keyword of entry.keywords ?? []) expect(keyword, entry.anchor).toBe(keyword.toLowerCase());
        }
    });

    it('uses label and help keys that exist, as text, in every language', () => {
        const problems: string[] = [];
        for (const language of LANGUAGES) {
            const dictionary = authoredLocale(language);
            for (const entry of SETTINGS_SEARCH_INDEX) {
                for (const key of [entry.labelKey, entry.helpKey]) {
                    if (key && (typeof message(dictionary, key) !== 'string' || message(dictionary, key) === '')) problems.push(`${language}: ${key}`);
                }
            }
        }
        expect(problems).toEqual([]);
    });
});
