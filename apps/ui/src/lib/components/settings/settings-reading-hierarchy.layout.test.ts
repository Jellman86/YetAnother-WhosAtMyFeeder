// @ts-nocheck: this source audit runs under Vitest's Node environment; Node types are
// intentionally absent from the browser application tsconfig.
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * How Settings reads: one heading scale and one place for weight. The page is the h1, the open
 * section an h2 that stays in view, each group an h3 (an h4 under More options), and a name inside a
 * card a subheading one level below its card. In a row the label is the one semibold thing: help,
 * values and links are regular. The display face has no weight under semibold, so text that must
 * read as regular is never left in it.
 */
const SETTINGS_DIR = __dirname;
const read = (...path: string[]): string => readFileSync(join(SETTINGS_DIR, ...path), 'utf8');
// The Health page's panel lives in this folder but is not part of Settings.
const NOT_SETTINGS = new Set(['SystemHealthPanel.svelte']);
const components = (): Array<[string, string]> =>
    ['', 'sections', '_primitives'].flatMap((dir) =>
        readdirSync(join(SETTINGS_DIR, dir))
            .filter((name) => name.endsWith('.svelte') && !NOT_SETTINGS.has(name))
            .map((name): [string, string] => [dir ? `${dir}/${name}` : name, read(dir, name)])
    );

describe('Settings heading hierarchy', () => {
    it('names the open section once, as the h2 that stays in view', () => {
        const page = read('_primitives', 'SettingsPage.svelte');
        expect(page).toMatch(/<header bind:this=\{sectionHeading\} class="settings-section-heading sticky [^"]*" data-settings-section-heading>\s*<h2 id="settings-section-title" class="text-2xl font-bold text-strong">\{sectionTitle\}<\/h2>/);
        // What scrolls to or takes focus stops below it.
        expect(page).toContain('root.style.scrollPaddingTop');
        // It is in the page before the status, so on a phone no heading comes before it.
        expect(page.indexOf('data-settings-section-heading')).toBeLessThan(page.indexOf('data-settings-aside="top"'));
    });

    it('makes a group an h3, and an h4 under More options, in the display face', () => {
        const card = read('_primitives', 'SettingsCard.svelte');
        expect(card).toContain("const tag = $derived(underPageTitle ? 'h2' : nested ? 'h4' : 'h3');");
        // Only the Health page's panel, which has no section heading above it, sits under the page title.
        const underTitle = components().filter(([, source]) => /<SettingsCard\b[^>]*\bunderPageTitle\b/.test(source)).map(([name]) => name);
        expect(underTitle).toEqual([]);
        expect(read('SystemHealthPanel.svelte')).toMatch(/<SettingsCard\s+underPageTitle\b/);
        expect(card).toContain('<svelte:element this={tag} id={headingId} class="font-display font-semibold text-strong {nested ? \'text-lg\' : \'text-xl\'}">');
        expect(card).toContain('provideSubheadingLevel(() => (nested ? 5 : 4));');
        const more = read('sections', 'SectionMore.svelte');
        expect(more).toContain('<h3 class="text-xl font-semibold text-strong">');
    });

    it('leaves every other heading to the shared primitives, so no level is chosen by hand', () => {
        const own: Record<string, RegExp> = {
            '_primitives/SettingsPage.svelte': /<h2\b/g,
            'sections/SectionMore.svelte': /<h3\b/g,
            'sections/SectionAside.svelte': /<h3\b/g,
            // Groups under More options that are not cards: a beta feature, and Garden's alerts.
            'BetaFeatureCard.svelte': /<h4\b/g,
            'sections/AlertsSection.svelte': /<h4\b/g
        };
        const offenders: string[] = [];
        for (const [name, source] of components()) {
            const allowed = own[name];
            for (const heading of source.matchAll(/<h[1-6]\b/g)) {
                if (!allowed || !heading[0].match(new RegExp(allowed.source))) offenders.push(`${name}: ${heading[0]}`);
            }
        }
        expect(offenders, 'Use SettingsCard for a group and SettingsSubheading for a name inside one').toEqual([]);
        expect(read('_primitives', 'SettingsSubheading.svelte')).toContain('<svelte:element this={`h${level}`} {id} class="font-sans font-semibold text-strong');
    });
});

describe('Settings weights', () => {
    it('keeps bold for the section name alone', () => {
        const offenders: string[] = [];
        for (const [name, source] of components()) {
            for (const match of source.matchAll(/class="([^"]*\bfont-(?:bold|black|extrabold)\b[^"]*)"/g)) {
                if (name === '_primitives/SettingsPage.svelte' && match[1] === 'text-2xl font-bold text-strong') continue;
                offenders.push(`${name}: ${match[1].slice(0, 70)}`);
            }
        }
        expect(offenders).toEqual([]);
    });

    it('makes the label the one semibold thing in a row: help and values are regular', () => {
        const row = read('_primitives', 'SettingsRow.svelte');
        expect(row).toContain('<span class="block text-base font-semibold text-strong" data-settings-row-label>{label}</span>');
        expect(row).toMatch(/<span id=\{descriptionId\} class="mt-1 block max-w-prose text-sm leading-snug text-muted">/);
        const slider = read('_primitives', 'SettingsSlider.svelte');
        expect(slider).toContain('<label for={id} class="block text-base font-semibold text-strong" data-settings-row-label>{label}</label>');
        expect(slider).toMatch(/<p id=\{descriptionId\} class="mt-1 max-w-prose text-sm leading-snug text-muted">/);
        expect(slider).toContain('<p class="text-right text-sm tabular-nums text-ink" aria-hidden="true">{shown}</p>');
    });

    it('never leaves help text in the display face, which has no regular weight', () => {
        // Text inside a heading takes the display face; a line meant as regular names the reading face.
        expect(read('sections', 'SectionMore.svelte')).toContain('<span class="block max-w-prose font-sans text-sm font-normal text-muted wrap-break-word">{summary}</span>');
        expect(read('sections', 'SectionAside.svelte')).not.toMatch(/text-left font-semibold text-accent-ink/);
    });

    it('lifts a group off the page with the kit\'s panel elevation', () => {
        const css = readFileSync(join(SETTINGS_DIR, '..', '..', '..', 'app.css'), 'utf8');
        const body = css.slice(css.indexOf('@utility settings-section-body {'));
        expect(body.slice(0, body.indexOf('}'))).toContain('box-shadow: var(--elevation-panel);');
    });
});
