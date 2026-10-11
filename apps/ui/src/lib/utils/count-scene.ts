import type { BirdObservation, SnapshotCandidate } from '../api';

/**
 * Birds are counted on one whole frame, which need not be the frame the photograph came from.
 * Their boxes are pixels of that frame, so an outline is only drawn on that exact retained
 * scene at its full resolution: never on the portrait, another moment, or a resized thumbnail.
 */

type SceneUnavailableReason =
    | 'no_birds'
    | 'mixed_frames'
    | 'no_scene'
    | 'ambiguous_scene'
    | 'cropped_scene'
    | 'thumbnail_only';

export type CountSceneResolution =
    | { status: 'ready'; candidate: SnapshotCandidate; imageUrl: string; clipVariant: string; frameIndex: number }
    | { status: 'unavailable'; reason: SceneUnavailableReason };

export interface SourceSize {
    width: number;
    height: number;
}

/** Observation IDs from a whole-frame scan carry the exact scene they were found on. */
const OBSERVED_IN_SCENE = /^(.+)__observed__\d+$/;
/** Frigate's own snapshot may already be cropped or resized by its configuration. */
const POSSIBLY_CROPPED_SOURCE = 'hq_candidate_frigate_snapshot_fallback';
/** Detector boxes are floats rounded from frame pixels. */
const EDGE_TOLERANCE_PX = 0.5;

export function resolveCountScene(
    birds: readonly BirdObservation[],
    candidates: readonly SnapshotCandidate[]
): CountSceneResolution {
    if (birds.length === 0) return { status: 'unavailable', reason: 'no_birds' };
    const { clip_variant: clipVariant, frame_index: frameIndex } = birds[0];
    if (birds.some((item) => item.clip_variant !== clipVariant || item.frame_index !== frameIndex)) {
        return { status: 'unavailable', reason: 'mixed_frames' };
    }

    const namedScenes = new Set(
        birds.flatMap((item) => {
            const match = OBSERVED_IN_SCENE.exec(item.candidate_id);
            return match ? [match[1]] : [];
        })
    );
    if (namedScenes.size > 1) return { status: 'unavailable', reason: 'ambiguous_scene' };

    const sameFrame = candidates.filter(
        (item) =>
            item.source_mode === 'full_frame' &&
            item.clip_variant === clipVariant &&
            item.frame_index === frameIndex
    );
    const [namedScene] = [...namedScenes];
    const matches = namedScene ? sameFrame.filter((item) => item.candidate_id === namedScene) : sameFrame;
    if (matches.length === 0) return { status: 'unavailable', reason: 'no_scene' };
    if (matches.length > 1) return { status: 'unavailable', reason: 'ambiguous_scene' };

    const [scene] = matches;
    if (scene.snapshot_source === POSSIBLY_CROPPED_SOURCE) return { status: 'unavailable', reason: 'cropped_scene' };
    if (!scene.image_url) {
        return { status: 'unavailable', reason: scene.thumbnail_url ? 'thumbnail_only' : 'no_scene' };
    }
    return { status: 'ready', candidate: scene, imageUrl: scene.image_url, clipVariant, frameIndex };
}

function validSize(size: SourceSize): boolean {
    return Number.isFinite(size.width) && Number.isFinite(size.height) && size.width > 0 && size.height > 0;
}

function boxFits(box: readonly number[], size: SourceSize): boolean {
    if (box.length !== 4 || !box.every(Number.isFinite)) return false;
    const [left, top, right, bottom] = box;
    return (
        right > left &&
        bottom > top &&
        left >= -EDGE_TOLERANCE_PX &&
        top >= -EDGE_TOLERANCE_PX &&
        right <= size.width + EDGE_TOLERANCE_PX &&
        bottom <= size.height + EDGE_TOLERANCE_PX
    );
}

/**
 * The decoded size of the full-resolution scene is its coordinate space. A box outside it
 * means the image is not the frame the boxes were measured on, so nothing is outlined.
 */
export function sceneGeometryIsValid(birds: readonly BirdObservation[], size: SourceSize): boolean {
    return validSize(size) && birds.every((item) => boxFits(item.crop_box, size));
}

export function sceneBoxPercent(
    box: readonly number[],
    size: SourceSize,
    frameAspectRatio = size.width / size.height
): { left: number; top: number; width: number; height: number } {
    const [left, top, right, bottom] = box;
    const imageAspectRatio = size.width / size.height;
    const widthFraction = Math.min(1, imageAspectRatio / frameAspectRatio);
    const heightFraction = Math.min(1, frameAspectRatio / imageAspectRatio);
    return {
        left: ((1 - widthFraction) / 2 + (left / size.width) * widthFraction) * 100,
        top: ((1 - heightFraction) / 2 + (top / size.height) * heightFraction) * 100,
        width: ((right - left) / size.width) * widthFraction * 100,
        height: ((bottom - top) / size.height) * heightFraction * 100
    };
}

/** A square crop cut from the scene by CSS, so each bird costs no extra request. */
export function cropBackground(
    box: readonly number[],
    size: SourceSize,
    edge: number
): { scale: number; offsetX: number; offsetY: number; width: number; height: number } {
    const [left, top, right, bottom] = box;
    // A little of the surroundings helps recognition; the stored box itself is unchanged.
    const span = Math.max(right - left, bottom - top) * 1.3;
    const scale = edge / span;
    return {
        scale,
        offsetX: edge / 2 - ((left + right) / 2) * scale,
        offsetY: edge / 2 - ((top + bottom) / 2) * scale,
        width: size.width * scale,
        height: size.height * scale
    };
}

function centre(item: BirdObservation): [number, number] {
    const [left = 0, top = 0, right = 0, bottom = 0] = item.crop_box;
    return [(left + right) / 2, (top + bottom) / 2];
}

/** Left to right across the scene, the way a person reads it. */
export function birdReadingOrder(birds: readonly BirdObservation[]): BirdObservation[] {
    return [...birds].sort((a, b) => {
        const [ax, ay] = centre(a);
        const [bx, by] = centre(b);
        return ax - bx || ay - by || a.id - b.id;
    });
}

function speciesKey(species: string): string {
    return species.trim().replace(/\s+/g, ' ').toLocaleLowerCase();
}

/**
 * Where a repeated species sits among its namesakes, counted from the left, so two House
 * Finches stay two findable birds. Null when the species appears once.
 */
export function repeatedSpeciesPositions(
    birds: readonly BirdObservation[]
): Map<number, { ordinal: number; total: number } | null> {
    const groups = new Map<string, BirdObservation[]>();
    for (const item of birdReadingOrder(birds)) {
        const key = speciesKey(item.species);
        groups.set(key, [...(groups.get(key) ?? []), item]);
    }
    const positions = new Map<number, { ordinal: number; total: number } | null>();
    for (const group of groups.values()) {
        group.forEach((item, index) => {
            positions.set(item.id, group.length > 1 ? { ordinal: index + 1, total: group.length } : null);
        });
    }
    return positions;
}

/**
 * Fallback for retained responses from older servers. Current responses carry the server's
 * decision, which includes configured unknown labels and noncanonical taxa.
 */
const UNKNOWN_LABELS = new Set(
    [
        'Unknown Bird',
        'Unknown',
        'No detection',
        'No detections',
        'No data',
        'No result',
        'No results',
        'No classification',
        'No classifications',
        'No bird',
        'Not a bird',
        'Unclassified',
        'Unidentified',
        'Unidentified bird',
        'N/A',
        'None',
        'Null'
    ].map(speciesKey)
);

export function isUnknownBirdLabel(species: string): boolean {
    return UNKNOWN_LABELS.has(speciesKey(species));
}

export function isUnknownBird(bird: BirdObservation): boolean {
    return bird.is_unknown ?? isUnknownBirdLabel(bird.species);
}

export function captureBirdCounts(birds: readonly BirdObservation[]): {
    counted: number;
    unknown: number;
    excluded: number;
    species: number;
} {
    const counted = birds.filter((item) => !item.is_hidden);
    const named = counted.filter((item) => !isUnknownBird(item));
    return {
        counted: counted.length,
        unknown: counted.length - named.length,
        excluded: birds.length - counted.length,
        species: new Set(named.map((item) => speciesKey(item.species))).size
    };
}
