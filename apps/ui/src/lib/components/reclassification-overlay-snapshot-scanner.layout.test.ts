import { describe, expect, it } from 'vitest';
import overlaySource from './ReclassificationOverlay.svelte?raw';
import scannerSource from './SnapshotAnalysisScanner.svelte?raw';

describe('ReclassificationOverlay snapshot analysis presentation', () => {
    it('uses a snapshot scanner instead of the video film reel for snapshot fallback work', () => {
        expect(overlaySource).toContain("import SnapshotAnalysisScanner from './SnapshotAnalysisScanner.svelte'");
        expect(overlaySource).toContain('{#if hasFallenBackToSnapshot}');
        expect(overlaySource).toContain('<SnapshotAnalysisScanner');
        expect(overlaySource).toContain('{:else}');
        expect(overlaySource).toContain('<VideoAnalysisFilmReel');
    });

    it('renders a scanning sweep over the current snapshot image', () => {
        expect(scannerSource).toContain('snapshot-analysis-scanner');
        expect(scannerSource).toContain('snapshot-analysis-sweep');
        expect(scannerSource).toContain("detection.reclassification.snapshot_scanning");
        expect(scannerSource).toContain('motion-reduce:animate-none');
    });
});
