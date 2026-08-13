import { describe, expect, it } from 'vitest';
import type { SnapshotCandidate } from '../api';
import { findMatchingFullFrameCandidate } from './detection-evidence';

function candidate(
    candidateId: string,
    sourceMode: string,
    frameIndex: number,
    clipVariant = 'event',
    selected = false
): SnapshotCandidate {
    return {
        candidate_id: candidateId,
        source_mode: sourceMode,
        frame_index: frameIndex,
        clip_variant: clipVariant,
        ranking_score: 0.8,
        selected
    };
}

describe('findMatchingFullFrameCandidate', () => {
    it('pairs the stored crop with the full frame from the same clip moment', () => {
        const candidates = [
            candidate('different-full', 'full_frame', 4),
            candidate('stored-crop', 'model_crop', 12, 'recording', true),
            candidate('matching-full', 'full_frame', 12, 'recording')
        ];

        expect(findMatchingFullFrameCandidate(candidates, 'stored-crop')?.candidate_id).toBe(
            'matching-full'
        );
    });

    it('does not offer an unrelated frame as the uncropped counterpart', () => {
        const candidates = [
            candidate('stored-crop', 'model_crop', 12, 'recording', true),
            candidate('other-full', 'full_frame', 4, 'event')
        ];

        expect(findMatchingFullFrameCandidate(candidates, 'stored-crop')).toBeNull();
    });

    it('uses the selected candidate when the API has no current candidate id', () => {
        const candidates = [
            candidate('selected-crop', 'frigate_hint_crop', 8, 'event', true),
            candidate('selected-full', 'full_frame', 8)
        ];

        expect(findMatchingFullFrameCandidate(candidates, null)?.candidate_id).toBe('selected-full');
    });

    it('does not offer a crop toggle when the stored snapshot is already a full frame', () => {
        const candidates = [candidate('stored-full', 'full_frame', 8, 'event', true)];

        expect(findMatchingFullFrameCandidate(candidates, 'stored-full')).toBeNull();
    });
});
