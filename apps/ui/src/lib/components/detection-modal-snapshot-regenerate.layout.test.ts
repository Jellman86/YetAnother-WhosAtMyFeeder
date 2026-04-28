import { describe, expect, it } from 'vitest';
import detectionModalSource from './DetectionModal.svelte?raw';

describe('DetectionModal snapshot regeneration', () => {
    it('offers regeneration from the empty snapshot-candidate state', () => {
        const emptyStateIndex = detectionModalSource.indexOf("allSnapshotFrameCandidates.length === 0");
        expect(emptyStateIndex).toBeGreaterThan(0);
        const populatedStateIndex = detectionModalSource.indexOf("modelSnapshotCandidates.length === 0", emptyStateIndex);
        expect(populatedStateIndex).toBeGreaterThan(emptyStateIndex);
        const emptyStateSource = detectionModalSource.slice(emptyStateIndex, populatedStateIndex);

        expect(emptyStateSource).toContain('handleGenerateSnapshotCandidates');
        expect(emptyStateSource).toContain('detection.snapshot_regenerate');
        expect(emptyStateSource).toContain('Regenerate snapshots');
    });

    it('distinguishes regeneration success from no selectable candidates', () => {
        expect(detectionModalSource).toContain('detection.snapshot_regenerate_no_candidates');
        expect(detectionModalSource).toContain('snapshotCandidates.length > 0');
    });

    it('avoids duplicate regenerate actions when the candidate list is empty', () => {
        expect(detectionModalSource).toContain('canGenerateSnapshotCandidates && allSnapshotFrameCandidates.length > 0');
    });

    it('does not apply regeneration results to a different detection after async work', () => {
        expect(detectionModalSource).toContain('const eventId = detection.frigate_event');
        expect(detectionModalSource).toContain('generateHighQualityBirdCropSnapshot(eventId)');
        expect(detectionModalSource).toContain('detection.frigate_event !== eventId');
    });
});
