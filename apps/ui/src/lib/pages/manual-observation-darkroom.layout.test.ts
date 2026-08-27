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

    it('lets you compare the scored input against the original upload', () => {
        expect(manualObservationSource).toContain("let evidenceView = $state<'scored' | 'original'>");
        expect(manualObservationSource).toContain('canCompareEvidence');
        expect(manualObservationSource).toContain('manual_observation.evidence.original');
        expect(manualObservationSource).toContain('aria-pressed={evidenceView === ');
        // The toggle is meaningless unless the model actually scored a crop.
        expect(manualObservationSource).toContain('topPrediction?.input_is_cropped');
    });

    it('only offers the original when it is an image the browser can show', () => {
        expect(manualObservationSource).toContain("draft.media_type === 'image'");
    });

    it('says which input was scored rather than leaving it implied', () => {
        expect(manualObservationSource).toContain('manual_observation.evidence.scored_help');
        expect(manualObservationSource).toContain('manual_observation.evidence.input');
        expect(manualObservationSource).toContain('manual_observation.evidence.file');
    });

    it('names the confirm action by the species being added', () => {
        expect(manualObservationSource).toContain('manual_observation.review.save_species');
        expect(manualObservationSource).toContain(': confirmLabel}</button>');
    });

    it('keeps the toggle keyboard operable at the touch-target floor', () => {
        expect(manualObservationSource).toMatch(/aria-pressed=\{evidenceView === 'scored'\}/);
        expect(manualObservationSource).toMatch(/min-h-11 rounded-full px-3 text-xs font-bold/);
        expect(manualObservationSource).toContain('focus-ring');
    });
});
