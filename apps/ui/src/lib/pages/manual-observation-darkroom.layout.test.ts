import { describe, expect, it } from 'vitest';

import manualObservationSource from './ManualObservation.svelte?raw';

describe('manual observation evidence review', () => {
    it('gives the evidence the larger half of the review step', () => {
        expect(manualObservationSource).toContain('data-manual-observation-evidence');
        // Media first, decision rail second.
        expect(manualObservationSource).toContain(
            'xl:grid-cols-[minmax(0,1.35fr)_minmax(20rem,.85fr)]'
        );
    });

    it('shows the photo of the species you are confirming, not the first frame (#481)', () => {
        // A video can hold several species; each suggestion carries its own best frame.
        expect(manualObservationSource).toContain('findPredictionForSpecies(draft?.predictions ?? [], selectedLabel)');
        expect(manualObservationSource).toContain('selectedPrediction?.photo_url');
        expect(manualObservationSource).toContain('src={evidenceImageUrl');
        expect(manualObservationSource).toContain('data-manual-observation-suggestion-photo');
        expect(manualObservationSource).toContain('manual_observation.review.several_species');
    });

    it('lets you check the crop against the whole frame it came from', () => {
        expect(manualObservationSource).toContain('selectedPrediction?.scene_url');
        expect(manualObservationSource).toContain("aria-pressed={evidenceView === 'bird'}");
        expect(manualObservationSource).toContain("aria-pressed={evidenceView === 'scene'}");
        expect(manualObservationSource).toContain('manual_observation.evidence.whole_frame');
        // Choosing another species reopens on its bird without an effect syncing state.
        expect(manualObservationSource).toContain('wholeFrameShownFor === selectedPrediction.label');
    });

    it('says what the photo is instead of claiming it is the scored input', () => {
        // The old caption called the uploaded photo "the exact input the classifier scored",
        // which was untrue whenever the classifier scored a crop.
        expect(manualObservationSource).not.toContain('manual_observation.evidence.scored_help');
        expect(manualObservationSource).toContain('manual_observation.evidence.no_species_frame_help');
        expect(manualObservationSource).toContain('manual_observation.evidence.photo_cropped_help');
        expect(manualObservationSource).toContain('manual_observation.evidence.input');
        expect(manualObservationSource).toContain('manual_observation.evidence.file');
    });

    it('names the confirm action by the species being added, in its friendly name', () => {
        expect(manualObservationSource).toContain('manual_observation.review.save_species');
        expect(manualObservationSource).toContain('values: { species: selectedSpeciesName }');
        expect(manualObservationSource).toContain(': confirmLabel}</button>');
    });

    it('keeps the toggle keyboard operable at the touch-target floor', () => {
        expect(manualObservationSource).toMatch(/aria-pressed=\{evidenceView === 'bird'\}/);
        expect(manualObservationSource).toMatch(/min-h-11 rounded-full px-3 text-xs font-bold/);
        expect(manualObservationSource).toContain('focus-ring');
    });
});
