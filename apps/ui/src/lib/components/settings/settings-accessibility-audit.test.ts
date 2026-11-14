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

/** Every quoted string in the markup and script, with its file and line, for class checks. */
function quotedStrings(): { where: string; text: string }[] {
    const found: { where: string; text: string }[] = [];
    for (const file of settingsSources()) {
        const source = readFileSync(file, 'utf8').replace(/<style[\s\S]*?<\/style>/g, '');
        for (const match of source.matchAll(/"[^"\n]*"|'[^'\n]*'|`[^`]*`/g)) {
            const line = source.slice(0, match.index).split('\n').length;
            const where = `${relative(SETTINGS_DIR, file)}:${line}`;
            found.push({ where, text: match[0] });
            // Each branch of a conditional class is its own colour, so each is checked alone too.
            if (match[0].startsWith('"')) {
                for (const branch of match[0].matchAll(/'[^']*'/g)) found.push({ where, text: branch[0] });
            }
        }
    }
    return found;
}

describe('Settings text in both themes', () => {
    it('gives every grey text tone its own dark-theme tone, so it never stays dark on a dark card', () => {
        // slate-500 to slate-700 read on white, but measure about 2.5:1 on the dark cards.
        const offenders = quotedStrings()
            .filter(({ text }) => /(?<![\w:-])text-slate-(500|600|700)\b/.test(text) && !/\bdark:text-/.test(text))
            .map(({ where, text }) => `${where} ${text.slice(0, 90)}`);
        expect(offenders).toEqual([]);
    });

    it('uses no faint tone for text in the light theme', () => {
        // slate-300/400 and the 400/500 tones of red, rose and amber measure 2.1 to 3.5:1 on white;
        // slate-500 and red and rose 600 fall under 4.5:1 on the tinted wells.
        const faint = /(?<![\w:-])text-(slate-(300|400|500)|(red|rose|amber|accent)-(400|500)|(red|rose)-600)\b/;
        const offenders = quotedStrings()
            .filter(({ text }) => faint.test(text))
            .map(({ where, text }) => `${where} ${text.slice(0, 90)}`);
        expect(offenders).toEqual([]);
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
        // The kit's colour is `ring-focus`, offset against `surface` so it reads in both themes.
        const ring = /\b(?:focus|focus-visible|focus-within):ring-(?:brand-|offset-(?:slate|white|gray))|\bdark:focus(?:-visible|-within)?:ring-offset-/;
        const offenders = quotedStrings()
            .filter(({ text }) => ring.test(text))
            .map(({ where, text }) => `${where} ${text.slice(0, 90)}`);
        expect(offenders).toEqual([]);
    });
});

