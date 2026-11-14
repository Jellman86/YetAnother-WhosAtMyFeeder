// @ts-nocheck: uses node:fs/node:path at vitest runtime; their types are not in the app tsconfig.
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

// Source rules that keep Settings legible and named in both themes. axe checks the rendered page;
// these catch the same mistakes in markup that a scan only reaches once a section is opened.

const SETTINGS_DIR = __dirname;
// The Health tab's body lives in pages/Errors.svelte.
const EXTRA_FILES = [join(__dirname, '../../pages/Settings.svelte'), join(__dirname, '../../pages/Errors.svelte')];

function settingsSources(dir = SETTINGS_DIR): string[] {
    const files: string[] = [];
    for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) files.push(...settingsSources(full));
        else if (entry.endsWith('.svelte')) files.push(full);
    }
    return dir === SETTINGS_DIR ? [...files, ...EXTRA_FILES] : files;
}

/**
 * The class strings in one file's source: every quoted string outside a <style> block, and every
 * attribute value whole, so a class list written over several lines is read as one. Each branch
 * of a conditional class is its own colour, so each is listed alone too.
 */
export function classStringsIn(source: string): { line: number; text: string }[] {
    const found: { line: number; text: string }[] = [];
    // Stylesheet text is CSS, not markup classes: strings inside a <style> block are skipped.
    const styleBlocks = [...source.matchAll(/<style\b[\s\S]*?<\/style>/g)].map((block) => [block.index, block.index + block[0].length]);
    const inStyle = (index: number): boolean => styleBlocks.some(([start, end]) => index >= start && index < end);
    const add = (index: number, text: string): void => {
        if (inStyle(index)) return;
        const line = source.slice(0, index).split('\n').length;
        found.push({ line, text });
        if (text.startsWith('"')) {
            for (const branch of text.matchAll(/'[^']*'/g)) found.push({ line, text: branch[0] });
        }
    };
    for (const match of source.matchAll(/"[^"\n]*"|'[^'\n]*'|`[^`]*`/g)) add(match.index, match[0]);
    // An attribute value that spans lines is missed above, where a quoted string stops at a newline.
    for (const match of source.matchAll(/[\w:-]+=("[^"]*\n[^"]*")/g)) add(match.index + match[0].indexOf('"'), match[1]);
    return found;
}

/** Every class string in Settings, with its file and line. */
function quotedStrings(): { where: string; text: string }[] {
    return settingsSources().flatMap((file) =>
        classStringsIn(readFileSync(file, 'utf8')).map(({ line, text }) => ({ where: `${relative(SETTINGS_DIR, file)}:${line}`, text })));
}

/** The rules, named so the regression cases below run exactly what the audit runs. */
export const RULES = {
    // slate-500 to slate-700 read on white, but measure about 2.5:1 on the dark cards.
    greyWithoutDarkTone: (text: string): boolean => /(?<![\w:-])text-slate-(500|600|700)\b/.test(text) && !/\bdark:text-/.test(text),
    // slate-300/400 and the 400/500 tones of red, rose and amber measure 2.1 to 3.5:1 on white;
    // slate-500 and red and rose 600 fall under 4.5:1 on the tinted wells.
    faintTone: (text: string): boolean => /(?<![\w:-])text-(slate-(300|400|500)|(red|rose|amber|accent)-(400|500)|(red|rose)-600)\b/.test(text),
    // The kit's colour is `ring-focus`, offset against `surface` so it reads in both themes.
    handRolledRing: (text: string): boolean =>
        /\b(?:focus|focus-visible|focus-within):ring-(?:brand-|offset-(?:slate|white|gray))|\bdark:focus(?:-visible|-within)?:ring-offset-/.test(text)
};

const offendersOf = (rule: (text: string) => boolean): string[] =>
    quotedStrings().filter(({ text }) => rule(text)).map(({ where, text }) => `${where} ${text.replace(/\s+/g, ' ').slice(0, 90)}`);

describe('the audit reads class lists the way they are written', () => {
    const multiLine = `<button
    type="button"
    class="rounded-2xl border-2 transition-all
           focus:outline-hidden focus:ring-2 focus:ring-brand-400
           {active ? 'bg-brand-700 text-white' : 'text-slate-600'}"
>`;

    it('finds a hand-rolled ring in a class list written over several lines', () => {
        expect(classStringsIn(multiLine).some(({ text }) => RULES.handRolledRing(text))).toBe(true);
    });

    it('reports it on the line the attribute starts, and checks its conditional branches alone', () => {
        const strings = classStringsIn(multiLine);
        expect(strings.find(({ text }) => RULES.handRolledRing(text))?.line).toBe(3);
        expect(strings.some(({ text }) => text === "'text-slate-600'" && RULES.greyWithoutDarkTone(text))).toBe(true);
    });

    it('leaves stylesheet text alone', () => {
        expect(classStringsIn('<style>\n  .x { content: "text-slate-400\n" }\n</style>')).toEqual([]);
    });
});

describe('Settings text in both themes', () => {
    it('gives every grey text tone its own dark-theme tone, so it never stays dark on a dark card', () => {
        expect(offendersOf(RULES.greyWithoutDarkTone)).toEqual([]);
    });

    it('uses no faint tone for text in the light theme', () => {
        expect(offendersOf(RULES.faintTone)).toEqual([]);
    });
});

describe('Settings names and structure', () => {
    it('names an option tile by the words on it, never by a label that replaces them', () => {
        const offenders = settingsSources()
            .filter((file) => /ariaLabelTemplate/.test(readFileSync(file, 'utf8')))
            .map((file) => relative(SETTINGS_DIR, file));
        expect(offenders).toEqual([]);
    });

    it('leaves the one h1 to the page title; the outline below it is walked in the browser', () => {
        // browser-tests/settings-outline.spec.ts checks every tab, sections open, for skipped levels.
        const offenders = settingsSources()
            .filter((file) => /<h1\b/.test(readFileSync(file, 'utf8')))
            .map((file) => relative(SETTINGS_DIR, file));
        expect(offenders).toEqual([]);
    });
});

describe('Settings controls from the shared kit', () => {
    it('draws every switch with the kit track and thumb, whose off state and focus ring pass', () => {
        const toggle = readFileSync(join(SETTINGS_DIR, '_primitives/SettingsToggle.svelte'), 'utf8');
        expect(toggle).toMatch(/class="switch-track\b/);
        expect(toggle).toContain('class="switch-thumb"');
        expect(toggle).not.toMatch(/bg-slate-[0-9]{3}|translate-x-5|focus(-visible)?:ring-brand/);
    });

    it('shows keyboard focus with the kit ring, never a hand-rolled brand ring', () => {
        expect(offendersOf(RULES.handRolledRing)).toEqual([]);
    });
});

