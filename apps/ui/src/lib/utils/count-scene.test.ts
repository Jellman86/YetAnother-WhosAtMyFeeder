import { describe, expect, it } from 'vitest';
import type { BirdObservation, SnapshotCandidate } from '../api';
import {
    birdReadingOrder,
    captureBirdCounts,
    cropBackground,
    isUnknownBirdLabel,
    repeatedSpeciesPositions,
    resolveCountScene,
    sceneBoxPercent,
    sceneGeometryIsValid
} from './count-scene';

const SCENE = 'replay-cardinal__full_frame__f150__d1bed4edc3';

function bird(id: number, box: number[], overrides: Partial<BirdObservation> = {}): BirdObservation {
    return {
        id,
        bird_index: id - 1,
        candidate_id: `${SCENE}__observed__${id}`,
        clip_variant: 'event',
        frame_index: 150,
        crop_box: box,
        detector_confidence: 0.8,
        species: 'House Finch',
        classifier_label: 'House Finch',
        classifier_score: 0.9,
        manual_species: false,
        is_hidden: false,
        ...overrides
    };
}

function candidate(id: string, overrides: Partial<SnapshotCandidate> = {}): SnapshotCandidate {
    return {
        candidate_id: id,
        source_mode: 'full_frame',
        clip_variant: 'event',
        frame_index: 150,
        ranking_score: 0.5,
        selected: false,
        snapshot_source: 'hq_candidate_full_frame',
        image_url: `/api/frigate/e/snapshot/candidates/${id}/image.jpg?v=1`,
        thumbnail_url: `/api/frigate/e/snapshot/candidates/${id}/thumbnail.jpg?v=1`,
        ...overrides
    };
}

// The reporter's Cardinal Intensive replay: portrait from frame 75, birds counted on frame 150.
const cardinalBirds = [
    bird(3, [858, 1151, 967, 1352], { species: 'Unknown Bird', classifier_label: 'Poecile hudsonicus', classifier_score: 0.27 }),
    bird(4, [1454, 1265, 1642, 1494], { species: 'Cardinalis cardinalis', classifier_label: 'Cardinalis cardinalis' })
];
const cardinalCandidates = [
    candidate('replay-cardinal__model_crop__f75__adde5fc428', { source_mode: 'model_crop', frame_index: 75, crop_box: [1418, 1231, 1673, 1517], selected: true }),
    candidate('replay-cardinal__full_frame__f75__0000000000', { frame_index: 75 }),
    candidate(SCENE)
];

describe('resolveCountScene', () => {
    it('resolves the exact count frame named by the observations, not the portrait frame', () => {
        const scene = resolveCountScene(cardinalBirds, cardinalCandidates);
        expect(scene.status).toBe('ready');
        if (scene.status !== 'ready') return;
        expect(scene.candidate.candidate_id).toBe(SCENE);
        expect(scene.frameIndex).toBe(150);
        expect(scene.imageUrl).toContain('/image.jpg');
    });

    it('never uses the resized thumbnail as a coordinate source', () => {
        const scene = resolveCountScene(cardinalBirds, [candidate(SCENE, { image_url: null })]);
        expect(scene).toEqual({ status: 'unavailable', reason: 'thumbnail_only' });
    });

    it('requires the same clip variant as well as the frame number', () => {
        const scene = resolveCountScene(cardinalBirds, [candidate(SCENE, { clip_variant: 'recording' })]);
        expect(scene).toEqual({ status: 'unavailable', reason: 'no_scene' });
    });

    it('refuses an ambiguous scene when observations do not name one', () => {
        const unnamed = cardinalBirds.map((item) => ({ ...item, candidate_id: `model-crop-${item.id}` }));
        expect(resolveCountScene(unnamed, [candidate('a'), candidate('b')])).toEqual({
            status: 'unavailable',
            reason: 'ambiguous_scene'
        });
        const single = resolveCountScene(unnamed, [candidate('a')]);
        expect(single.status).toBe('ready');
    });

    it('refuses a named scene that is not retained, even when another full frame matches', () => {
        expect(resolveCountScene(cardinalBirds, [candidate('other-full-frame')])).toEqual({
            status: 'unavailable',
            reason: 'no_scene'
        });
    });

    it('refuses observations from different frames or naming different scenes', () => {
        const mixed = [cardinalBirds[0], { ...cardinalBirds[1], frame_index: 75 }];
        expect(resolveCountScene(mixed, cardinalCandidates)).toEqual({ status: 'unavailable', reason: 'mixed_frames' });
        const twoScenes = [cardinalBirds[0], { ...cardinalBirds[1], candidate_id: 'elsewhere__observed__0' }];
        expect(resolveCountScene(twoScenes, cardinalCandidates)).toEqual({
            status: 'unavailable',
            reason: 'ambiguous_scene'
        });
    });

    it('refuses a Frigate snapshot fallback that may already be cropped', () => {
        const scene = resolveCountScene(cardinalBirds, [
            candidate(SCENE, { snapshot_source: 'hq_candidate_frigate_snapshot_fallback' })
        ]);
        expect(scene).toEqual({ status: 'unavailable', reason: 'cropped_scene' });
    });

    it('has nothing to resolve without observations', () => {
        expect(resolveCountScene([], cardinalCandidates)).toEqual({ status: 'unavailable', reason: 'no_birds' });
    });
});

describe('scene geometry', () => {
    const fullSize = { width: 3840, height: 2160 };

    it('accepts boxes inside the decoded full-resolution scene', () => {
        expect(sceneGeometryIsValid(cardinalBirds, fullSize)).toBe(true);
    });

    it('rejects a resized image whose decoded size cannot hold the frame-pixel boxes', () => {
        expect(sceneGeometryIsValid(cardinalBirds, { width: 960, height: 540 })).toBe(false);
    });

    it.each([
        ['zero size', [10, 10, 20, 20], { width: 0, height: 2160 }],
        ['non-finite size', [10, 10, 20, 20], { width: Number.NaN, height: 2160 }],
        ['inverted box', [20, 10, 10, 20], fullSize],
        ['empty box', [10, 10, 10, 20], fullSize],
        ['non-finite box', [10, Number.POSITIVE_INFINITY, 20, 20], fullSize],
        ['short box', [10, 10, 20], fullSize],
        ['negative box', [-40, 10, 20, 20], fullSize]
    ])('rejects %s', (_label, box, size) => {
        expect(sceneGeometryIsValid([bird(1, box as number[])], size)).toBe(false);
    });

    it('places a box as percentages of the scene it was measured on', () => {
        const percent = sceneBoxPercent([1454, 1265, 1642, 1494], fullSize);
        expect(percent.left).toBeCloseTo(37.865, 2);
        expect(percent.top).toBeCloseTo(58.565, 2);
        expect(percent.width).toBeCloseTo(4.896, 2);
        expect(percent.height).toBeCloseTo(10.602, 2);
    });

    it('frames a crop thumbnail around the bird without enlarging the stored box', () => {
        const crop = cropBackground([858, 1151, 967, 1352], fullSize, 48);
        // The taller side (201px) plus a margin fills the square, so the scene is scaled down.
        expect(crop.scale).toBeGreaterThan(0);
        expect(crop.scale * 201).toBeLessThan(48);
        const centreX = (858 + 967) / 2;
        expect(-crop.offsetX + 24).toBeCloseTo(centreX * crop.scale, 3);
    });
});

describe('labels and counts', () => {
    it('reads birds left to right, with id as the tie-break', () => {
        const order = birdReadingOrder([bird(9, [500, 0, 600, 100]), bird(2, [100, 0, 200, 100]), bird(1, [500, 0, 600, 100])]);
        expect(order.map((item) => item.id)).toEqual([2, 1, 9]);
    });

    it('distinguishes repeated species by position and leaves single species alone', () => {
        const finches = [
            bird(1, [900, 0, 1000, 100]),
            bird(2, [100, 0, 200, 100]),
            bird(3, [500, 0, 600, 100], { species: 'Unknown Bird' }),
            bird(4, [1500, 0, 1600, 100], { species: 'house finch', is_hidden: true })
        ];
        const positions = repeatedSpeciesPositions(finches);
        expect(positions.get(2)).toEqual({ ordinal: 1, total: 3 });
        expect(positions.get(1)).toEqual({ ordinal: 2, total: 3 });
        expect(positions.get(4)).toEqual({ ordinal: 3, total: 3 });
        expect(positions.get(3)).toBeNull();
    });

    it('counts stored decisions: exclusions out, Unknown separate, repeated species kept', () => {
        const counts = captureBirdCounts([
            bird(1, [0, 0, 1, 1]),
            bird(2, [0, 0, 1, 1]),
            bird(3, [0, 0, 1, 1], { species: 'Unknown Bird' }),
            bird(4, [0, 0, 1, 1], { species: 'Blue Jay', manual_species: true, classifier_score: 0.1 }),
            bird(5, [0, 0, 1, 1], { species: 'Northern Cardinal', is_hidden: true })
        ]);
        expect(counts).toEqual({ counted: 4, unknown: 1, excluded: 1, species: 2 });
    });

    it.each(['Unknown Bird', 'unknown', ' Unidentified bird ', 'Not a bird'])('treats %s as unknown', (label) => {
        expect(isUnknownBirdLabel(label)).toBe(true);
    });

    it('does not treat a named species as unknown', () => {
        expect(isUnknownBirdLabel('Cardinalis cardinalis')).toBe(false);
    });

    it('honours server unknown decisions for configured labels and noncanonical taxa', () => {
        const observations = [
            { ...bird(1, [0, 0, 1, 1]), is_unknown: true },
            { ...bird(2, [1, 0, 2, 1], { species: 'Life (Life)' }), is_unknown: true },
            bird(3, [2, 0, 3, 1], { species: 'Blue Jay', manual_species: true, classifier_score: 0.1 })
        ];
        expect(captureBirdCounts(observations)).toEqual({ counted: 3, unknown: 2, excluded: 0, species: 1 });
    });
});
