import { describe, expect, it } from 'vitest';
import overlaySource from './ReclassificationOverlay.svelte?raw';

describe('ReclassificationOverlay terminal outcome', () => {
    it('makes a completed run with no result explicitly visible', () => {
        expect(overlaySource).toContain("progress.outcome === 'no_result'");
        expect(overlaySource).toContain('detection.reclassification.unchanged_title');
        expect(overlaySource).toContain('detection.reclassification.unchanged_description');
        expect(overlaySource).toContain('detection.reclassification.unchanged_evidence');
        expect(overlaySource).toContain(
            'supporting: strongestEvidence.top_candidates?.[0]?.supporting_frames ?? 0'
        );
        expect(overlaySource).toContain(
            'independent: strongestEvidence.independent_frames ?? strongestEvidence.evaluated_frames'
        );
    });

    it('does not present an abstention as a final species result', () => {
        expect(overlaySource).toContain('isComplete && hasFinalResult');
    });
});
