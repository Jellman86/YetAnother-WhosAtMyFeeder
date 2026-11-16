import { describe, expect, it } from 'vitest';
import { getBirdNames } from './naming';

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

    it('leaves a real name that merely contains the words alone', () => {
        expect(getBirdNames({ display_name: 'Unknown Bird of Paradise' }, true, false).primary).toBe('Unknown Bird of Paradise');
    });
});
