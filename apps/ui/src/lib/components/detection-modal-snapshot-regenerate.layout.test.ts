import { describe, expect, it } from 'vitest';
import detectionModalSource from './DetectionModal.svelte?raw';
import stripSource from './FrameStrip.svelte?raw';

describe('DetectionModal snapshot regeneration', () => {
    it('offers regeneration at the end of the moment strip', () => {
        const railIndex = detectionModalSource.indexOf('data-detection-inline-frame-picker');
        expect(railIndex).toBeGreaterThan(0);
        const railSource = detectionModalSource.slice(railIndex, railIndex + 1400);

        expect(railSource).toContain("canRegenerate={Boolean(snapshotStatus?.high_quality_bird_crop_enabled)}");
        expect(railSource).toContain('onregenerate={() => { void handleGenerateSnapshotCandidates(); }}');
        expect(stripSource).toContain('{#if canRegenerate && onregenerate}');
        expect(stripSource).toContain('detection.snapshot_regenerate');
        expect(stripSource).toContain('Regenerate snapshots');
    });

    it('distinguishes regeneration success from no selectable candidates', () => {
        expect(detectionModalSource).toContain('detection.snapshot_regenerate_no_candidates');
        expect(detectionModalSource).toContain('snapshotCandidates.length > 0');
        expect(detectionModalSource).toContain("result.status === 'existing_crop_preserved'");
        expect(detectionModalSource).toContain('detection.snapshot_existing_crop_preserved');
        expect(detectionModalSource).toContain("result.status === 'generated_hq_snapshot'");
        expect(detectionModalSource).toContain('detection.snapshot_generated_full_frame');
    });

    it('exposes one regenerate control rather than duplicating it by candidate state', () => {
        expect(detectionModalSource.match(/void handleGenerateSnapshotCandidates\(\)/g)).toHaveLength(1);
        expect(stripSource.match(/onregenerate\?\.\(\)/g)).toHaveLength(1);
    });

    it('does not apply regeneration results to a different detection after async work', () => {
        expect(detectionModalSource).toContain('const eventId = detection.frigate_event');
        expect(detectionModalSource).toContain('generateHighQualityBirdCropSnapshot(eventId)');
        expect(detectionModalSource).toContain('detection.frigate_event !== eventId');
    });
});
