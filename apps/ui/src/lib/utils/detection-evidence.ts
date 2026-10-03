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

/** The crop regions visible in this exact whole frame, with the chosen crop first. */
export function sameFrameCropCandidates(
    candidates: SnapshotCandidate[],
    current: SnapshotCandidate | null
): SnapshotCandidate[] {
    if (!current?.crop_box || current.source_mode === 'full_frame') return [];

    const crops = [current, ...candidates.filter((candidate) =>
        candidate.candidate_id !== current.candidate_id &&
        candidate.clip_variant === current.clip_variant &&
        candidate.frame_index === current.frame_index &&
        candidate.source_mode !== 'full_frame' &&
        candidate.source_mode !== 'model_observation' &&
        candidate.crop_box?.length === 4
    )];
    const distinct: SnapshotCandidate[] = [];
    for (const crop of crops) {
        const cropBox = crop.crop_box;
        if (!cropBox || distinct.some((kept) =>
            kept.crop_box && cropBoxIoU(kept.crop_box, cropBox) >= 0.8
        )) continue;
        distinct.push(crop);
    }
    return distinct;
}

function cropBoxIoU(left: number[], right: number[]): number {
    const overlap = Math.max(0, Math.min(left[2], right[2]) - Math.max(left[0], right[0])) *
        Math.max(0, Math.min(left[3], right[3]) - Math.max(left[1], right[1]));
    const leftArea = Math.max(0, left[2] - left[0]) * Math.max(0, left[3] - left[1]);
    const rightArea = Math.max(0, right[2] - right[0]) * Math.max(0, right[3] - right[1]);
    const union = leftArea + rightArea - overlap;
    return union > 0 ? overlap / union : 0;
}
