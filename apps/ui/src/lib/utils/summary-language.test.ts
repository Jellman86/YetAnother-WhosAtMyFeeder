import { describe, expect, it } from 'vitest';
import { summaryInAnotherLanguage } from './summary-language';

const english = { extract: 'The house sparrow is a bird.', summary_language: 'en' };

describe('a description in a language other than the one being read', () => {
    it('is named, with its code for the text and its name in the reader\'s language', () => {
        expect(summaryInAnotherLanguage(english, 'de')).toEqual({ code: 'en', name: 'Englisch' });
        expect(summaryInAnotherLanguage(english, 'fr')).toEqual({ code: 'en', name: 'Anglais' });
        expect(summaryInAnotherLanguage({ extract: 'Ein Vogel.', summary_language: 'de' }, 'en')).toEqual({ code: 'de', name: 'German' });
    });

    it('is nothing to remark on when it is the reader\'s language, whatever the region', () => {
        expect(summaryInAnotherLanguage(english, 'en')).toBeNull();
        expect(summaryInAnotherLanguage(english, 'en-GB')).toBeNull();
        expect(summaryInAnotherLanguage({ extract: 'Uma ave.', summary_language: 'pt' }, 'pt-BR')).toBeNull();
    });

    it('claims nothing when the description does not say its language, or there is none', () => {
        expect(summaryInAnotherLanguage({ extract: 'A bird.', summary_language: null }, 'de')).toBeNull();
        expect(summaryInAnotherLanguage({ extract: 'A bird.' }, 'de')).toBeNull();
        expect(summaryInAnotherLanguage({ extract: null, summary_language: 'en' }, 'de')).toBeNull();
        expect(summaryInAnotherLanguage(null, 'de')).toBeNull();
    });

    it('still names the language when the reader\'s is not known', () => {
        expect(summaryInAnotherLanguage(english, null)).toBeNull();
        expect(summaryInAnotherLanguage({ extract: 'Ein Vogel.', summary_language: 'de' }, undefined)).toEqual({ code: 'de', name: 'German' });
    });
});
