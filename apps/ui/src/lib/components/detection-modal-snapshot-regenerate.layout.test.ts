import { describe, expect, it } from 'vitest';
import detectionModalSource from './DetectionModal.svelte?raw';

describe('DetectionModal snapshot regeneration', () => {
    it('offers regeneration directly from the inline rail', () => {
        const railIndex = detectionModalSource.indexOf('data-detection-inline-frame-picker');
        expect(railIndex).toBeGreaterThan(0);
        const railSource = detectionModalSource.slice(railIndex);

        expect(railSource).toContain('{:else if canGenerateSnapshotCandidates}');
        expect(railSource).toContain('handleGenerateSnapshotCandidates');
        expect(railSource).toContain('detection.snapshot_regenerate');
        expect(railSource).toContain('Regenerate snapshots');
    });

    it('distinguishes regeneration success from no selectable candidates', () => {
        expect(detectionModalSource).toContain('detection.snapshot_regenerate_no_candidates');
        expect(detectionModalSource).toContain('snapshotCandidates.length > 0');
    });

    it('exposes one regenerate control rather than duplicating it by candidate state', () => {
        expect(detectionModalSource.match(/onclick=\{\(event\) => \{ event\.stopPropagation\(\); void handleGenerateSnapshotCandidates\(\); \}\}/g)).toHaveLength(1);
    });

    it('does not apply regeneration results to a different detection after async work', () => {
        expect(detectionModalSource).toContain('const eventId = detection.frigate_event');
        expect(detectionModalSource).toContain('generateHighQualityBirdCropSnapshot(eventId)');
        expect(detectionModalSource).toContain('detection.frigate_event !== eventId');
    });
});
