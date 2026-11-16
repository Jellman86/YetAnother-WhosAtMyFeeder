import { describe, expect, it } from 'vitest';
import before from './settings-reachability.before.json';
import { canonicalSettingsPath, settingsPartPath, settingsSectionFromRoute, settingsSectionOfPart, type SettingsPart, type SettingsSection } from './settings-route';
import { settingsFieldPart, settingsFieldSection } from './settings-fields';

// Settings as it was before it was organised by task, frozen in settings-reachability.before.json:
// every former tab, the components it mounted with the props each received, the element ids those
// components rendered, and the tab that showed each saved field. This proves each is still
// reachable from the section the former tab now opens. A setting that moves on purpose is named in
// MOVED, so nothing is lost or renamed silently.

interface FormerTab {
    components: Record<string, string[]>;
    ids: string[];
}
const formerTabs = before.tabs as Record<SettingsPart, FormerTab>;
const formerHomes = before.savedFields as Record<string, SettingsPart>;

/** Fields or ids shown somewhere else on purpose, with the part that now shows them. */
const MOVED: Readonly<Record<string, SettingsPart>> = {};

const SECTION_FILES: Readonly<Record<SettingsSection, string>> = {
    cameras: '../components/settings/sections/CamerasSection.svelte',
    identification: '../components/settings/sections/IdentificationSection.svelte',
    alerts: '../components/settings/sections/AlertsSection.svelte',
    sharing: '../components/settings/sections/SharingSection.svelte',
    storage: '../components/settings/sections/StorageSection.svelte',
    display: '../components/settings/sections/DisplaySection.svelte'
};

const sources = import.meta.glob<string>(
    ['../components/**/*.svelte', '../pages/**/*.svelte', '../components/settings/sections/part-loaders.ts'],
    { query: '?raw', import: 'default', eager: true }
);

function source(path: string): string {
    const found = sources[path];
    if (found === undefined) throw new Error(`No source for ${path}`);
    return found;
}

/** `a/b/../c.svelte` written from `from` as a key of `sources`. */
function resolvePath(from: string, relative: string): string {
    const parts = from.split('/').slice(0, -1);
    for (const segment of relative.split('/')) {
        if (segment === '..') parts.pop();
        else if (segment !== '.') parts.push(segment);
    }
    return parts.join('/');
}

const loadersSource = source('../components/settings/sections/part-loaders.ts');
/** Each part loader's name and the component file it imports. */
const LOADER_FILES: ReadonlyMap<string, string> = new Map(
    [...loadersSource.matchAll(/export const (load\w+) = lazyComponent\(\(\) => import\('([^']+)'\)\)/g)].map(
        ([, loader, file]) => [loader, resolvePath('../components/settings/sections/part-loaders.ts', file)]
    )
);

function componentFile(name: string): string {
    const file = [...LOADER_FILES.values()].find((path) => path.endsWith(`/${name}.svelte`));
    if (!file) throw new Error(`No part loader imports ${name}`);
    return file;
}

/** The markup of one part inside its section file, from its wrapper to the next part's. */
function partMarkup(part: SettingsPart): string {
    const file = source(SECTION_FILES[settingsSectionOfPart(part)]);
    const start = file.indexOf(`data-settings-part="${part}"`);
    if (start < 0) throw new Error(`${part} has no place in its section`);
    const next = file.indexOf('data-settings-part="', start + 1);
    return file.slice(start, next < 0 ? undefined : next);
}

/** The text of the tag starting at `start`, up to its closing `>`, skipping `>` inside braces. */
function tagAt(text: string, start: number): string {
    let depth = 0;
    for (let index = start; index < text.length; index += 1) {
        const char = text[index];
        if (char === '{') depth += 1;
        else if (char === '}') depth -= 1;
        else if (char === '>' && depth === 0) return text.slice(start, index + 1);
    }
    throw new Error('unterminated tag');
}

/** The props a mounted component receives, by name: `bind:x`, `{x}`, `x={…}` and `x="…"`. */
function propsOf(tag: string): Set<string> {
    const names = new Set<string>();
    for (const [, name] of tag.matchAll(/(?:^|\s)(?:bind:)?([A-Za-z]\w*)(?==|\s|\/?>)/g)) names.add(name);
    for (const [, name] of tag.matchAll(/(?:^|\s)\{([A-Za-z]\w*)\}/g)) names.add(name);
    return names;
}

/** The keys of a LazyRoute's `props={{ … }}` object, with any spread written as `...name`. */
function propsObjectKeys(tag: string): Set<string> {
    const body = /props=\{\{([\s\S]*)\}\}/.exec(tag)?.[1] ?? '';
    const keys = new Set<string>();
    let depth = 0;
    let token = '';
    for (const char of `${body},`) {
        if ('{(['.includes(char)) depth += 1;
        if ('})]'.includes(char)) depth -= 1;
        if (char === ',' && depth === 0) {
            const entry = token.trim();
            if (entry) keys.add(entry.startsWith('...') ? entry : (/^(\w+)/.exec(entry)?.[1] ?? entry));
            token = '';
            continue;
        }
        token += char;
    }
    return keys;
}

/** What a part passes to a component: the props on its tag, or on the LazyRoute that loads it. */
function propsPassed(part: SettingsPart, component: string): Set<string> | null {
    const markup = partMarkup(part);
    const tagStart = markup.search(new RegExp(`<${component}\\b`));
    if (tagStart >= 0) return propsOf(tagAt(markup, tagStart));
    const loader = [...LOADER_FILES.entries()].find(([, file]) => file === componentFile(component))?.[0];
    const lazyStart = loader ? markup.indexOf(`loader={${loader}}`) : -1;
    if (lazyStart < 0) return null;
    const routeStart = markup.lastIndexOf('<LazyRoute', lazyStart);
    return propsObjectKeys(tagAt(markup, routeStart));
}

/** Every component file a section can render: its part loaders' components and what they import. */
function sectionTree(section: SettingsSection): string[] {
    const sectionFile = SECTION_FILES[section];
    const seen = new Set<string>([sectionFile]);
    const queue = [...source(sectionFile).matchAll(/\b(load\w+)\b/g)]
        .map(([, loader]) => LOADER_FILES.get(loader))
        .filter((file): file is string => Boolean(file));
    while (queue.length > 0) {
        const file = queue.pop() as string;
        if (seen.has(file) || !(file in sources)) continue;
        seen.add(file);
        for (const [, relative] of source(file).matchAll(/(?:from|import\()\s*'(\.[^']+\.svelte)'/g)) {
            queue.push(resolvePath(file, relative));
        }
    }
    return [...seen];
}

describe('every former Settings tab', () => {
    it('is frozen with what it held, so the comparison has something to prove', () => {
        expect(Object.keys(formerTabs)).toHaveLength(12);
        expect(Object.values(formerTabs).reduce((count, tab) => count + tab.ids.length, 0)).toBeGreaterThan(150);
        expect(Object.keys(formerHomes).length).toBeGreaterThan(190);
    });

    it.each(Object.keys(formerTabs) as SettingsPart[])('%s: its address opens the section that holds it, at its place', (part) => {
        const section = settingsSectionOfPart(part);
        expect(canonicalSettingsPath(`/settings/${part}`, '')).toBe(settingsPartPath(part));
        expect(canonicalSettingsPath('/settings', part)).toBe(settingsPartPath(part));
        expect(settingsSectionFromRoute(`/settings/${part}`)).toBe(section);
        expect(settingsPartPath(part)).toBe(`/settings/${section}#${part}`);
    });

    it.each(Object.keys(formerTabs) as SettingsPart[])('%s: each component it mounted is mounted in its part with every prop it had', (part) => {
        const problems: string[] = [];
        for (const [component, props] of Object.entries(formerTabs[part].components)) {
            const passed = propsPassed(part, component);
            if (!passed) {
                problems.push(`${component} is not mounted in the ${part} part`);
                continue;
            }
            for (const prop of props) if (!passed.has(prop)) problems.push(`${component} no longer receives ${prop}`);
        }
        expect(problems).toEqual([]);
    });

    it.each(Object.keys(formerTabs) as SettingsPart[])('%s: every element it rendered is still rendered by its section', (part) => {
        const tree = sectionTree(settingsSectionOfPart(part)).map(source).join('\n');
        const lost = formerTabs[part].ids.filter((id) => !MOVED[id] && !tree.includes(`id="${id}"`));
        expect(lost).toEqual([]);
    });
});

describe('every saved setting', () => {
    it.each(Object.entries(formerHomes))('%s is shown by the section its former tab moved to', (field, formerPart) => {
        const part = MOVED[field] ?? formerPart;
        expect(settingsFieldPart(field)).toBe(part);
        expect(settingsFieldSection(field)).toBe(settingsSectionOfPart(part));
    });
});
