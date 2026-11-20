// @ts-nocheck: read by source audits under Vitest's Node environment; Node types are
// intentionally absent from the browser application tsconfig.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

/**
 * Settings' markup as the audits need it: every row, slider and card with its anchor and keys, the
 * disclosures it sits inside, and every control with whether a row or a card's header holds it.
 * Read from every component under `components/settings`, subfolders included.
 */
export const SETTINGS_COMPONENTS_DIR = join(__dirname, '..', 'components', 'settings');

/** Components that hold no setting an owner looks for, each with its reason. */
const UNSEARCHED_COMPONENTS: Record<string, string> = {
    'SystemHealthPanel.svelte': 'shown on the Health page, not in Settings',
    'NativeProfileRevalidation.svelte': 'a notice that appears only after a crash, with no setting in it',
    'SettingsSearch.svelte': 'the search box itself',
    'SettingsTabs.svelte': 'the section list, which chooses a section and saves nothing',
    'AITestModal.svelte': 'a test dialog, not a setting',
    'DeviceCheckDialog.svelte': 'a test dialog, not a setting'
};

/** Ids a component takes from a shared constant instead of a literal. */
const CONSTANT_IDS: Record<string, string> = {
    RUNTIME_REPORT_SECTION_ID: 'detection-inference-advanced',
    CHANNELS_SECTION_ID: 'notification-channels'
};

const HOLDERS = ['SettingsCard', 'AdvancedSection'];
const ROWS = ['SettingsRow', 'SettingsSlider'];
const CONTROLS = ['SettingsToggle', 'SettingsInput', 'SettingsSelect', 'SecretInput', 'SettingsTextarea', 'SettingsSegmented', 'input', 'select', 'textarea'];
const ATTRIBUTES = String.raw`((?:[^>"'{}]|"[^"]*"|'[^']*'|\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})*)`;
const TOKEN = new RegExp(String.raw`<(\/?)(${[...HOLDERS, ...ROWS, ...CONTROLS].join('|')})\b${ATTRIBUTES}>|\{#snippet (\w+)|\{\/snippet\}`, 'g');

export interface MarkedRow {
    file: string;
    tag: string;
    anchor: string | null;
    labelKey: string | null;
    helpKey: string | null;
    /** Its anchor or label is an expression: a row built in a loop. */
    dynamic: boolean;
    /** A card that says it is under More options. */
    nested: boolean;
    /** The closable sections around it, outermost first. */
    within: string[];
}

export interface MarkedControl {
    file: string;
    tag: string;
    /** Inside a row, or beside a card's heading as that card's own switch. */
    held: boolean;
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

/** Every component under Settings, as a path from the Settings folder; the primitives define the controls and are left out. */
export function settingsComponentFiles(dir = SETTINGS_COMPONENTS_DIR): string[] {
    return readdirSync(dir).sort().flatMap((name) => {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) return name === '_primitives' ? [] : settingsComponentFiles(path);
        return name.endsWith('.svelte') && !(name in UNSEARCHED_COMPONENTS) ? [relative(SETTINGS_COMPONENTS_DIR, path)] : [];
    });
}

export function readSettingsMarkup(files = settingsComponentFiles(), read = (file: string): string => readFileSync(join(SETTINGS_COMPONENTS_DIR, file), 'utf8')): { rows: MarkedRow[]; controls: MarkedControl[] } {
    const rows: MarkedRow[] = [];
    const controls: MarkedControl[] = [];
    for (const file of files) {
        const source = read(file);
        const open: Array<string | null> = [];
        const snippets: string[] = [];
        let insideRows = 0;
        for (const match of source.matchAll(TOKEN)) {
            const [whole, closing, tag, attributes = '', snippet] = match;
            if (whole === '{/snippet}') {
                snippets.pop();
                continue;
            }
            if (snippet) {
                snippets.push(snippet);
                continue;
            }
            const selfClosing = attributes.trimEnd().endsWith('/');
            if (closing) {
                if (HOLDERS.includes(tag)) open.pop();
                if (tag === 'SettingsRow') insideRows -= 1;
                continue;
            }
            const within = open.filter((id): id is string => id !== null);
            if (HOLDERS.includes(tag)) {
                const { id, dynamic } = idOf(attribute(attributes, 'id'));
                const closable = tag === 'AdvancedSection' || /(?:^|\s)collapsible(?:\s|$)/.test(attributes);
                if (tag === 'SettingsCard') {
                    rows.push({ file, tag, anchor: id, labelKey: translationKey(attribute(attributes, 'title')), helpKey: null, dynamic, nested: /(?:^|\s)nested(?:\s|$)/.test(attributes), within });
                }
                if (!selfClosing) open.push(closable ? id : null);
                continue;
            }
            if (ROWS.includes(tag)) {
                const { id, dynamic } = idOf(attribute(attributes, tag === 'SettingsRow' ? 'labelId' : 'id'));
                const labelKey = translationKey(attribute(attributes, 'label'));
                rows.push({ file, tag, anchor: id, labelKey, helpKey: translationKey(attribute(attributes, 'description')), dynamic: dynamic || labelKey === null, nested: false, within });
                if (tag === 'SettingsRow' && !selfClosing) insideRows += 1;
                continue;
            }
            // A hidden input carries no setting; a control beside a card's heading is that card's own switch.
            if (tag === 'input' && /type="(?:hidden|file)"/.test(attributes)) continue;
            controls.push({ file, tag, held: insideRows > 0 || snippets.includes('actions') });
        }
    }
    return { rows, controls };
}
