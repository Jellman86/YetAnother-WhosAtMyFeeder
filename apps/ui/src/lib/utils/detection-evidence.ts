import type { SnapshotCandidate } from '../api';

/**
 * Return the uncropped view of the same clip moment as the stored candidate.
 * A full frame from another moment is different evidence, not a safe crop toggle.
 */
export function findMatchingFullFrameCandidate(
    candidates: SnapshotCandidate[],
    currentCandidateId: string | null
): SnapshotCandidate | null {
    const current =
        candidates.find((candidate) => candidate.candidate_id === currentCandidateId) ??
        candidates.find((candidate) => candidate.selected);

    if (!current || current.source_mode === 'full_frame') return null;

    return candidates.find(
        (candidate) =>
            candidate.source_mode === 'full_frame' &&
            candidate.frame_index === current.frame_index &&
            candidate.clip_variant === current.clip_variant
    ) ?? null;
}
