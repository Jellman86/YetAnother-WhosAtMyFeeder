import { describe, expect, it } from 'vitest';

import overlaySource from './DetectionCardAnalysisOverlay.svelte?raw';

describe('DetectionCardAnalysisOverlay layout', () => {
    it('uses compact card-specific copy and lighter visual weight', () => {
        expect(overlaySource).toContain("detection.card_analysis.finalizing");
        expect(overlaySource).toContain("default: 'Finalizing result'");
        expect(overlaySource).toContain("detection.card_analysis.finalizing_subtitle");
        expect(overlaySource).toContain("default: 'Applying the best match'");
        expect(overlaySource).toContain("detection.card_analysis.closing_soon");
        expect(overlaySource).toContain("card-analysis-close-indicator");
        expect(overlaySource).toContain("card-analysis-close-ring");
        expect(overlaySource).not.toContain("default: 'Closing soon'");
        expect(overlaySource).toContain("text-base font-black leading-none");
        expect(overlaySource).toContain("rounded-xl border border-white/10 bg-black/18 p-2.5");
        expect(overlaySource).not.toContain("text-lg font-black leading-none");
        expect(overlaySource).not.toContain("rounded-2xl border border-white/12 bg-black/25 p-3");
    });
});
