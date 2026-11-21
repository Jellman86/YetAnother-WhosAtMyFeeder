import { addMessages, init, locale } from 'svelte-i18n';
import { get } from 'svelte/store';
import { beforeAll, describe, expect, it } from 'vitest';
import { birdNames, getBirdNames } from './naming';
import namingSource from './naming.ts?raw';

const svelteSources = import.meta.glob('./**/*.svelte', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;

describe('getBirdNames', () => {
    it('leads with the common name and keeps the scientific name beneath it', () => {
        expect(getBirdNames({ display_name: 'Common Chaffinch', common_name: 'Buchfink', scientific_name: 'Fringilla coelebs' }, true, false)).toEqual({
            primary: 'Buchfink',
            secondary: 'Fringilla coelebs'
        });
    });

    it('names a visit the classifier could not name "Unknown bird", in one casing, wherever the placeholder arrives', () => {
        for (const placeholder of ['Unknown Bird', 'unknown bird', ' Unknown Bird ']) {
            expect(getBirdNames({ display_name: placeholder }, true, false).primary).toBe('Unknown bird');
            expect(getBirdNames({ species: placeholder }, true, true).primary).toBe('Unknown bird');
            expect(getBirdNames({ display_name: placeholder, common_name: placeholder }, true, false)).toEqual({
                primary: 'Unknown bird',
                secondary: null
            });
        }
    });

    it('prints the name it is given for an unknown bird, so the caller owns the language', () => {
        expect(getBirdNames({ display_name: 'Unknown Bird' }, true, false, 'Unbekannter Vogel').primary).toBe('Unbekannter Vogel');
    });

    it('leaves a real name that merely contains the words alone', () => {
        expect(getBirdNames({ display_name: 'Unknown Bird of Paradise' }, true, false).primary).toBe('Unknown Bird of Paradise');
    });
});

describe('birdNames, the namer a component reads', () => {
    beforeAll(async () => {
        addMessages('en', { common: { unknown_bird: 'Unknown bird' } });
        addMessages('de', { common: { unknown_bird: 'Unbekannter Vogel' } });
        await init({ fallbackLocale: 'en', initialLocale: 'en' });
    });

    it('renames an unknown bird for every subscriber when the language changes', async () => {
        // A helper that read the translator once kept "Unknown bird" on a German page until the
        // data happened to reload. A store re-runs whatever derived from it.
        const seen: string[] = [];
        const stop = birdNames.subscribe((names) => seen.push(names({ display_name: 'Unknown Bird' }, true, false).primary));
        expect(seen.at(-1)).toBe('Unknown bird');

        await locale.set('de');
        expect(seen.at(-1)).toBe('Unbekannter Vogel');
        expect(get(birdNames)({ species: 'Unknown Bird' }, true, true).primary).toBe('Unbekannter Vogel');

        await locale.set('en');
        expect(seen.at(-1)).toBe('Unknown bird');
        stop();
    });

    it('is the only way a component names a bird, and the pure helper reads no store', () => {
        const direct = Object.entries(svelteSources)
            .filter(([, source]) => /(?<![\w$.])getBirdNames\(/.test(source))
            .map(([file]) => file);
        expect(direct).toEqual([]);
        const helper = namingSource.slice(namingSource.indexOf('export function getBirdNames('));
        expect(helper).not.toMatch(/\bget\(/);
    });
});
