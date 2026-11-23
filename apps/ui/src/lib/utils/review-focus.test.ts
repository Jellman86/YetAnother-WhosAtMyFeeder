import { describe, expect, it } from 'vitest';
import type { BirdObservation, Detection, SnapshotCandidate } from '../api';
import { groupCandidatesIntoMoments } from './frame-moments';
import {
    computeCropViewport,
    findMatchingCropCandidateForBird,
    isBirdUncertain,
    partitionCountedBirdsForReview,
    partitionReviewMoments,
    shouldAutoFocusUncertainBird,
    singleUncertainBirdToSync
} from './review-focus';

function bird(id: number, overrides: Partial<BirdObservation> = {}): BirdObservation {
    return {
        id,
        bird_index: id - 1,
        candidate_id: `scene__observed__${id}`,
        clip_variant: 'recording',
        frame_index: 192,
        crop_box: [100, 100, 180, 180],
        detector_confidence: 0.9,
        species: 'Unknown Bird',
        classifier_label: 'Chroicocephalus ridibundus',
        classifier_score: 0.31,
        manual_species: false,
        is_hidden: false,
        is_unknown: true,
        tracked: false,
        identity_source: 'crop',
        identity_score: 0.31,
        ...overrides
    };
}

function candidate(id: string, overrides: Partial<SnapshotCandidate> = {}): SnapshotCandidate {
    return {
        candidate_id: id,
        frame_index: 192,
        frame_offset_seconds: 2,
        source_mode: 'model_crop',
        clip_variant: 'recording',
        crop_box: [100, 100, 180, 180],
        ranking_score: 0.5,
        selected: false,
        thumbnail_url: `/thumb/${id}.jpg`,
        image_url: `/image/${id}.jpg`,
        ...overrides
    } as SnapshotCandidate;
}

const rockPigeonDetection: Detection = {
    frigate_event: 'evt-multi',
    display_name: 'Rock Pigeon',
    common_name: 'Rock Pigeon',
    scientific_name: 'Columba livia',
    category_name: 'Columba livia',
    camera_name: 'Big greenhouse area',
    detection_time: '2026-11-18T07:57:08Z',
    score: 0.65
};

describe('review-focus multi-bird triage helpers', () => {
    it('identifies uncertain vs confident counted birds and partitions mixed captures', () => {
        const unknown = bird(1);
        const jackdaw = bird(2, {
            species: 'Corvus monedula',
            common_name: 'Western Jackdaw',
            scientific_name: 'Coloeus monedula',
            classifier_label: 'Corvus monedula',
            classifier_score: 0.81,
            identity_score: 0.81,
            is_unknown: false
        });
        const excluded = bird(3, { is_hidden: true });

        expect(isBirdUncertain(unknown, 0.7)).toBe(true);
        expect(isBirdUncertain(jackdaw, 0.7)).toBe(false);
        expect(isBirdUncertain(excluded, 0.7)).toBe(false);

        const part = partitionCountedBirdsForReview([unknown, jackdaw, excluded], 0.7);
        expect(part.hasMixedCertainty).toBe(true);
        expect(part.focusBirds.map((item) => item.id)).toEqual([1]);
        expect(part.confidentBystanders.map((item) => item.id)).toEqual([2]);
        expect(part.excludedBirds.map((item) => item.id)).toEqual([3]);
    });

    it('keeps all birds in focus when none are uncertain', () => {
        const confidentA = bird(1, { species: 'Rock Pigeon', is_unknown: false, classifier_score: 0.88, identity_score: 0.88 });
        const confidentB = bird(2, { species: 'Western Jackdaw', is_unknown: false, classifier_score: 0.91, identity_score: 0.91 });
        const part = partitionCountedBirdsForReview([confidentA, confidentB], 0.7);
        expect(part.hasMixedCertainty).toBe(false);
        expect(part.focusBirds.map((item) => item.id)).toEqual([1, 2]);
        expect(part.confidentBystanders).toEqual([]);
    });

    it('tucks confident crops of other species out of the primary review strip', () => {
        const moments = groupCandidatesIntoMoments([
            candidate('whole-1', { source_mode: 'full_frame', crop_box: null, selected: true, classifier_label: 'Columba livia', classifier_score: 0.55 }),
            candidate('gull-crop', { crop_box: [50, 50, 120, 120], classifier_label: 'Chroicocephalus ridibundus', classifier_common_name: 'Black-headed Gull', classifier_score: 0.31 }),
            candidate('jackdaw-crop', { crop_box: [500, 400, 620, 520], classifier_label: 'Corvus monedula', classifier_common_name: 'Western Jackdaw', classifier_scientific_name: 'Coloeus monedula', classifier_score: 0.9 }),
            candidate('pigeon-crop', { frame_index: 200, frame_offset_seconds: 3, crop_box: [300, 200, 420, 320], classifier_label: 'Columba livia', classifier_common_name: 'Rock Pigeon', classifier_score: 0.82 }),
            candidate('jackdaw-crop-2', { frame_index: 200, frame_offset_seconds: 3, crop_box: [700, 400, 820, 520], classifier_label: 'Corvus monedula', classifier_common_name: 'Western Jackdaw', classifier_scientific_name: 'Coloeus monedula', classifier_score: 0.86 })
        ]);

        const savedKey = moments.find((moment) => moment.whole?.candidate_id === 'whole-1' && moment.choice === 'whole')?.key ?? null;
        const result = partitionReviewMoments(moments, rockPigeonDetection, savedKey, 0.7);

        expect(result.otherConfidentMoments).toHaveLength(2);
        expect(result.otherConfidentMoments.every((moment) => moment.read?.label === 'Corvus monedula')).toBe(true);
        expect(result.otherSpecies).toEqual([
            {
                label: 'Corvus monedula',
                commonName: 'Western Jackdaw',
                scientificName: 'Coloeus monedula',
                count: 2,
                maxScore: 0.9
            }
        ]);
        expect(result.focusMoments).toHaveLength(3);
        expect(result.focusMoments.map((moment) => moment.position)).toEqual([1, 2, 3]);
    });

    it('never hides single-bird folded moments or the currently saved photograph', () => {
        const moments = groupCandidatesIntoMoments([
            candidate('single-whole', { source_mode: 'full_frame', crop_box: null }),
            candidate('single-crop', { crop_box: [100, 100, 200, 200], classifier_label: 'Corvus monedula', classifier_score: 0.95 })
        ]);
        const result = partitionReviewMoments(moments, rockPigeonDetection, null, 0.7);
        expect(result.otherConfidentMoments).toHaveLength(0);
        expect(result.focusMoments).toHaveLength(1);
    });

    it('selects the single unnamed uncertain bird to sync only on untied multi-bird captures', () => {
        const unknown = bird(1);
        const jackdaw = bird(2, { species: 'Western Jackdaw', is_unknown: false, classifier_score: 0.81, identity_score: 0.81 });
        expect(singleUncertainBirdToSync([unknown, jackdaw], 0.7)?.id).toBe(1);
        // Never sync when there are two unknown birds.
        expect(singleUncertainBirdToSync([unknown, bird(3)], 0.7)).toBeNull();
        // Never sync when a bird is already tracked by Frigate.
        expect(singleUncertainBirdToSync([unknown, { ...jackdaw, tracked: true }], 0.7)).toBeNull();
        // Never sync on a single-bird capture.
        expect(singleUncertainBirdToSync([unknown], 0.7)).toBeNull();
    });

    it('auto-focuses the single uncertain bird only when the saved photograph is a wide full frame', () => {
        const unknown = bird(1);
        const jackdaw = bird(2, { species: 'Western Jackdaw', is_unknown: false, classifier_score: 0.81, identity_score: 0.81 });
        const widePhoto = candidate('whole', { source_mode: 'full_frame', crop_box: null, selected: true });
        const croppedPhoto = candidate('crop', { source_mode: 'model_crop', crop_box: [10, 10, 80, 80], selected: true });

        expect(shouldAutoFocusUncertainBird(widePhoto, [unknown, jackdaw], 0.7)?.id).toBe(1);
        expect(shouldAutoFocusUncertainBird(croppedPhoto, [unknown, jackdaw], 0.7)).toBeNull();
        expect(shouldAutoFocusUncertainBird(widePhoto, [unknown], 0.7)).toBeNull();
    });

    it('matches a counted bird to its overlapping crop candidate', () => {
        const target = bird(1, { crop_box: [100, 100, 180, 180] });
        const exactMatch = candidate('crop-a', { crop_box: [98, 102, 182, 178] });
        const otherBird = candidate('crop-b', { crop_box: [600, 400, 700, 500] });
        const fullFrame = candidate('full', { source_mode: 'full_frame', crop_box: null });

        expect(findMatchingCropCandidateForBird(target, [fullFrame, otherBird, exactMatch])?.candidate_id).toBe('crop-a');
        expect(findMatchingCropCandidateForBird(target, [fullFrame, otherBird])).toBeNull();
    });

    it('computes a clamped padded crop viewport around a small bird', () => {
        const viewport = computeCropViewport([1200, 700, 1260, 760], { width: 2560, height: 1440 });
        expect(viewport).not.toBeNull();
        expect(viewport!.x).toBeGreaterThanOrEqual(0);
        expect(viewport!.y).toBeGreaterThanOrEqual(0);
        expect(viewport!.x + viewport!.width).toBeLessThanOrEqual(2560);
        expect(viewport!.y + viewport!.height).toBeLessThanOrEqual(1440);
        expect(viewport!.width).toBeGreaterThanOrEqual(180);

        // Corner bird stays inside frame bounds.
        const corner = computeCropViewport([0, 0, 40, 40], { width: 1280, height: 720 });
        expect(corner).toEqual({ x: 0, y: 0, width: 240, height: 180 });
    });
});
