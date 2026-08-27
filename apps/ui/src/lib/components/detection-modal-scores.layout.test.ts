import { describe, expect, it } from 'vitest';
import detectionModalSource from './DetectionModal.svelte?raw';
import en from '../i18n/locales/en.json';

/**
 * #269: "there is a frigate score and the real score, that is quite confusing
 * for the user. They probably have no idea what Frigate even is".
 *
 * Two percentages sit on one panel measuring different things: how sure the
 * camera was that it saw a bird at all, and how sure the classifier is about
 * which species. Only one of them was labelled, and it was labelled with the
 * name of a product rather than with what it measures.
 */
// en.json nests deeper than two levels in places, so narrow just the branch
// this test reads rather than asserting a shape for the whole file.
const detectionStrings = (en as unknown as { detection: Record<string, string> }).detection;

describe('the two scores on a detection', () => {
    it('labels the camera score by what it measures, not by the product', () => {
        // Its neighbours are "Seen", "Conditions" and "Heard nearby": plain
        // language, no vendor. This was the only fact naming one.
        expect(detectionStrings.fact_frigate).not.toMatch(/frigate/i);
        expect(detectionStrings.fact_frigate.toLowerCase()).toContain('bird');
    });

    it('explains what the camera score is, and that it is not the species score', () => {
        expect(detectionStrings.fact_frigate_hint).toBeTruthy();
        expect(detectionStrings.fact_frigate_hint.toLowerCase()).toContain('species');
        expect(detectionModalSource).toContain("detection.fact_frigate_hint");
    });

    it('names the species score instead of leaving it an unlabelled percentage', () => {
        // "92% confident" next to a name does not say confident of what, which
        // is half of why the two numbers read as one inconsistent number.
        expect(detectionStrings.fact_species_match).toBeTruthy();
        expect(detectionModalSource).toContain("detection.fact_species_match");
    });

    it('drops the retired FRIGATE percentage string', () => {
        expect(detectionStrings.frigate_score).toBeUndefined();
    });
});
