import { describe, expect, it } from 'vitest';
import detectionSource from './DetectionModal.svelte?raw';
import gardenSource from './GardenCaptureModal.svelte?raw';
import speciesSource from './SpeciesDetailModal.svelte?raw';

// A description can arrive in a language other than the page's (the taxon's linked article, when
// the reader's language has none). Every place that prints one says which language it is in and
// marks the text, so it is neither mistaken for a translation nor read aloud in the wrong voice.
describe.each([
    ['the bird record', detectionSource],
    ['the Garden record', gardenSource],
    ['species details', speciesSource]
])('a description in another language on %s', (_surface, source) => {
    it('is marked with its language for assistive technology', () => {
        expect(source).toContain("import { summaryInAnotherLanguage } from '../utils/summary-language';");
        expect(source).toMatch(/lang=\{summaryLanguage\?\.code\}/);
    });

    it('is labelled in words, through i18n, only when it differs from the page language', () => {
        expect(source).toContain('{#if summaryLanguage}');
        expect(source).toContain("$_('species_detail.summary_language_note'");
        expect(source).toContain('values: { language: summaryLanguage.name }');
        expect(source).toContain('data-reference-summary-language={summaryLanguage.code}');
    });
});
