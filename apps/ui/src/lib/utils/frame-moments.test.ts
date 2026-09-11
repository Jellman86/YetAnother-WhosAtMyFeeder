import { describe, expect, it } from 'vitest';
import type { SnapshotCandidate } from '../api';
import {
    AS_RECORDED_KEY,
    currentMoment,
    formatOffset,
    groupCandidatesIntoMoments,
    momentThumbnailUrl,
    preferredCandidate,
    wholeSceneOutline
} from './frame-moments';

function candidate(overrides: Partial<SnapshotCandidate>): SnapshotCandidate {
    return {
        candidate_id: 'c',
        frame_index: 1,
        frame_offset_seconds: 1,
        source_mode: 'full_frame',
        clip_variant: 'event',
        ranking_score: 0.5,
        selected: false,
        thumbnail_url: '/thumb/c.jpg',
        image_url: '/image/c.jpg',
        ...overrides
    } as SnapshotCandidate;
}

describe('groupCandidatesIntoMoments (#256)', () => {
    it('folds the framings of one frame into one moment, closest on the bird shown', () => {
        const moments = groupCandidatesIntoMoments([
            candidate({ candidate_id: 'whole-3', frame_index: 3, frame_offset_seconds: 4.2, source_mode: 'full_frame' }),
            candidate({ candidate_id: 'hint-3', frame_index: 3, frame_offset_seconds: 4.2, source_mode: 'frigate_hint_crop', ranking_score: 0.7 }),
            candidate({ candidate_id: 'model-3', frame_index: 3, frame_offset_seconds: 4.2, source_mode: 'model_crop', ranking_score: 0.6 })
        ]);

        expect(moments).toHaveLength(1);
        expect(moments[0].crop?.candidate_id).toBe('model-3');
        expect(moments[0].whole?.candidate_id).toBe('whole-3');
        expect(preferredCandidate(moments[0])?.candidate_id).toBe('model-3');
        expect(momentThumbnailUrl(moments[0])).toBe('/thumb/c.jpg');
    });

    it('orders moments by time, not by ranking', () => {
        const moments = groupCandidatesIntoMoments([
            candidate({ candidate_id: 'late', frame_index: 9, frame_offset_seconds: 9.5, ranking_score: 0.99 }),
            candidate({ candidate_id: 'early', frame_index: 2, frame_offset_seconds: 1.0, ranking_score: 0.1 })
        ]);

        expect(moments.map((moment) => moment.whole?.candidate_id)).toEqual(['early', 'late']);
        expect(moments.map((moment) => moment.position)).toEqual([1, 2]);
    });

    it('keeps the same frame index apart across clip variants', () => {
        const moments = groupCandidatesIntoMoments([
            candidate({ candidate_id: 'event-1', frame_index: 1, clip_variant: 'event' }),
            candidate({ candidate_id: 'visit-1', frame_index: 1, clip_variant: 'full_visit', frame_offset_seconds: 30 })
        ]);
        expect(moments).toHaveLength(2);
    });

    it('leads with the camera\'s own snapshot when it is still available', () => {
        const moments = groupCandidatesIntoMoments(
            [candidate({ candidate_id: 'a', frame_index: 1 })],
            { asRecordedAvailable: true }
        );
        expect(moments[0].key).toBe(AS_RECORDED_KEY);
        expect(moments[0].asRecorded).toBe(true);
        expect(moments[0].position).toBe(1);
        expect(moments[1].position).toBe(2);
    });

    it('reports the read the model was most sure about for the moment', () => {
        const [moment] = groupCandidatesIntoMoments([
            candidate({ candidate_id: 'w', frame_index: 1, classifier_label: 'Dunnock', classifier_score: 0.41 }),
            candidate({ candidate_id: 'c', frame_index: 1, source_mode: 'model_crop', classifier_label: 'Blue Tit', classifier_score: 0.89 }),
            candidate({ candidate_id: 'h', frame_index: 1, source_mode: 'frigate_hint_crop', classifier_label: null })
        ]);
        expect(moment.read).toEqual({ label: 'Blue Tit', score: 0.89 });
    });

    it('has no read when no candidate carries a label', () => {
        const [moment] = groupCandidatesIntoMoments([candidate({ candidate_id: 'w', classifier_label: null })]);
        expect(moment.read).toBeNull();
    });
});

describe('currentMoment', () => {
    const moments = groupCandidatesIntoMoments(
        [
            candidate({ candidate_id: 'whole-1', frame_index: 1, source_mode: 'full_frame' }),
            candidate({ candidate_id: 'crop-1', frame_index: 1, source_mode: 'model_crop' }),
            candidate({ candidate_id: 'whole-2', frame_index: 2, frame_offset_seconds: 5 })
        ],
        { asRecordedAvailable: true }
    );

    it('finds the moment through either of its framings', () => {
        expect(currentMoment(moments, 'crop-1', 'model_crop')?.frameIndex).toBe(1);
        expect(currentMoment(moments, 'whole-1', 'full_frame')?.frameIndex).toBe(1);
    });

    it('resolves the camera snapshot by source rather than by candidate id', () => {
        expect(currentMoment(moments, null, 'frigate_snapshot')?.asRecorded).toBe(true);
    });

    it('is null when the photograph is none of the moments', () => {
        expect(currentMoment(moments, 'missing', 'model_crop')).toBeNull();
        expect(currentMoment(moments, null, null)).toBeNull();
    });
});

describe('formatOffset', () => {
    it('reads as minutes and seconds', () => {
        expect(formatOffset(7.4)).toBe('0:07');
        expect(formatOffset(65)).toBe('1:05');
        expect(formatOffset(0)).toBe('0:00');
    });

    it('is null for an unknown offset', () => {
        expect(formatOffset(null)).toBeNull();
        expect(formatOffset(-1)).toBeNull();
        expect(formatOffset(Number.NaN)).toBeNull();
    });
});

describe('wholeSceneOutline', () => {
    it('lands on the bird, not on the letterbox bars', () => {
        // A 1600x900 frame shown in a 800x600 box draws at 800x450, offset 75px down.
        const outline = wholeSceneOutline([400, 225, 800, 675], { width: 1600, height: 900 }, { width: 800, height: 600 });
        expect(outline).toEqual({ left: 200, top: 75 + 112.5, width: 200, height: 225 });
    });

    it('clamps a box that runs off the frame', () => {
        const outline = wholeSceneOutline([-50, -50, 100, 100], { width: 100, height: 100 }, { width: 100, height: 100 });
        expect(outline).toEqual({ left: 0, top: 0, width: 100, height: 100 });
    });

    it('is null without a usable box or size', () => {
        expect(wholeSceneOutline(null, { width: 10, height: 10 }, { width: 10, height: 10 })).toBeNull();
        expect(wholeSceneOutline([0, 0, 0, 0], { width: 10, height: 10 }, { width: 10, height: 10 })).toBeNull();
        expect(wholeSceneOutline([0, 0, 5, 5], { width: 0, height: 10 }, { width: 10, height: 10 })).toBeNull();
    });
});
