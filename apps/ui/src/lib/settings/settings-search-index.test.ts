// @ts-nocheck: this source audit runs under Vitest's Node environment; Node types are
// intentionally absent from the browser application tsconfig.
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { authoredLocale } from '../i18n/authored-locales';
import { SETTINGS_SECTION_ORDER } from './settings-route';
import { settingsMoreId } from './settings-more';
import { SETTINGS_SEARCH_INDEX, settingsSearchEntry } from './settings-search-index';

/**
 * The search index against the markup it describes. A setting added to a Settings component
 * without an entry fails here, as does an entry whose label, help, anchor or disclosure no longer
 * matches the row; the browser suite then proves each entry lands where it says.
 */
const COMPONENTS_DIR = join(__dirname, '..', 'components', 'settings');
const LANGUAGES = ['en', 'de', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'zh'];

/** Components whose groups are not settings an owner looks for, each with its reason. */
const UNSEARCHED_COMPONENTS: Record<string, string> = {
    'SystemHealthPanel.svelte': 'shown on the Health page, not in Settings',
    'NativeProfileRevalidation.svelte': 'a notice that appears only after a crash, with no setting in it'
};

/** Rows built in a loop, whose anchors and labels are not literals; each is indexed by hand. */
const LOOPED_ROWS: Record<string, string[]> = {
    'AccessibilitySettings.svelte': ['setting-high-contrast', 'setting-dyslexia-font', 'setting-reduced-motion', 'setting-live-announcements'],
    'HaWeatherSettings.svelte': [
        'setting-ha-weather-temperature', 'setting-ha-weather-wind-speed', 'setting-ha-weather-wind-direction', 'setting-ha-weather-cloud-cover',
        'setting-ha-weather-precipitation', 'setting-ha-weather-rain', 'setting-ha-weather-snowfall'
    ]
};

/** Ids a component takes from a shared constant instead of a literal. */
const CONSTANT_IDS: Record<string, string> = {
    RUNTIME_REPORT_SECTION_ID: 'detection-inference-advanced',
    CHANNELS_SECTION_ID: 'notification-channels'
};

const TAG = /<(\/?)(SettingsRow|SettingsSlider|SettingsCard|AdvancedSection)\b((?:[^>"'{}]|"[^"]*"|'[^']*'|\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})*)>/g;

interface Found {
    file: string;
    tag: string;
    anchor: string | null;
    labelKey: string | null;
    helpKey: string | null;
    dynamic: boolean;
    within: string[];
}

function attribute(attributes: string, name: string): { literal?: string; expression?: string } | null {
    const literal = new RegExp(`(?:^|\\s)${name}="([^"]*)"`).exec(attributes);
    if (literal) return { literal: literal[1] };
    const expression = new RegExp(`(?:^|\\s)${name}=\\{((?:[^{}]|\\{(?:[^{}]|\\{[^{}]*\\})*\\})*)\\}`).exec(attributes);
    return expression ? { expression: expression[1] } : null;
}

function translationKey(value: { literal?: string; expression?: string } | null): string | null {
    const match = value?.expression ? /^\s*\$_\(\s*'([^']+)'/.exec(value.expression) : null;
    return match ? match[1] : null;
}

function idOf(value: { literal?: string; expression?: string } | null): { id: string | null; dynamic: boolean } {
    if (!value) return { id: null, dynamic: false };
    if (value.literal !== undefined) return value.literal.includes('{') ? { id: null, dynamic: true } : { id: value.literal, dynamic: false };
    const constant = CONSTANT_IDS[value.expression.trim()];
    return constant ? { id: constant, dynamic: false } : { id: null, dynamic: true };
}

function readComponents(): Found[] {
    const found: Found[] = [];
    for (const file of readdirSync(COMPONENTS_DIR).filter((name) => name.endsWith('.svelte')).sort()) {
        if (file in UNSEARCHED_COMPONENTS) continue;
        const source = readFileSync(join(COMPONENTS_DIR, file), 'utf8');
        const open: Array<string | null> = [];
        for (const match of source.matchAll(TAG)) {
            const [, closing, tag, attributes] = match;
            const holds = tag === 'SettingsCard' || tag === 'AdvancedSection';
            if (closing) {
                if (holds) open.pop();
                continue;
            }
            const within = open.filter((id): id is string => id !== null);
            if (holds) {
                const { id, dynamic } = idOf(attribute(attributes, 'id'));
                const closable = tag === 'AdvancedSection' || /(?:^|\s)collapsible(?:\s|$)/.test(attributes);
                if (tag === 'SettingsCard') {
                    found.push({ file, tag, anchor: id, labelKey: translationKey(attribute(attributes, 'title')), helpKey: null, dynamic, within });
                }
                if (!attributes.trimEnd().endsWith('/')) open.push(closable ? id : null);
                continue;
            }
            const { id, dynamic } = idOf(attribute(attributes, tag === 'SettingsRow' ? 'labelId' : 'id'));
            const labelKey = translationKey(attribute(attributes, 'label'));
            found.push({ file, tag, anchor: id, labelKey, helpKey: translationKey(attribute(attributes, 'description')), dynamic: dynamic || labelKey === null, within });
        }
    }
    return found;
}

const allSources = (): string =>
    [COMPONENTS_DIR, join(COMPONENTS_DIR, 'sections'), __dirname]
        .flatMap((dir) => readdirSync(dir).filter((name) => /\.(svelte|ts)$/.test(name) && !name.includes('.test.') && !name.startsWith('settings-search-index')).map((name) => readFileSync(join(dir, name), 'utf8')))
        .join('\n');

function message(dictionary: unknown, key: string): unknown {
    let node = dictionary;
    for (const part of key.split('.')) node = node && typeof node === 'object' ? node[part] : undefined;
    return node;
}

describe('the settings search index', () => {
    const found = readComponents();

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
        // A row built in a loop is indexed by hand, and only where that is declared.
        expect(Object.keys(looped).sort()).toEqual(Object.keys(LOOPED_ROWS).sort());
        for (const anchors of Object.values(LOOPED_ROWS)) for (const anchor of anchors) expect(settingsSearchEntry(anchor), anchor).not.toBeNull();
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
            // A looped row's id is `setting-` and the loop's own id; a beta feature's heading is named from its id.
            const looped = /^setting-(?:ha-weather-)?(.+)$/.exec(id);
            if (looped && sources.includes(`id: '${looped[1]}'`)) return true;
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
