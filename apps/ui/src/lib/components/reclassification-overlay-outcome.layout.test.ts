import { describe, expect, it } from 'vitest';
import overlaySource from './ReclassificationOverlay.svelte?raw';

describe('ReclassificationOverlay terminal outcome', () => {
    it('makes a completed run with no result explicitly visible', () => {
        expect(overlaySource).toContain("progress.outcome === 'no_result'");
        expect(overlaySource).toContain('detection.reclassification.unchanged_title');
        expect(overlaySource).toContain('detection.reclassification.unchanged_description');
        expect(overlaySource).toContain('detection.reclassification.unchanged_evidence');
    });

    it('does not present an abstention as a final species result', () => {
        expect(overlaySource).toContain('isComplete && hasFinalResult');
    });
});
