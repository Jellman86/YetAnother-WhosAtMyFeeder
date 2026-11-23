import type { BirdObservation, Detection, SnapshotCandidate } from '../api';
import { isUnknownBird, isUnknownBirdLabel, type SourceSize } from './count-scene';
import type { FrameMoment } from './frame-moments';

export const DEFAULT_REVIEW_CONFIDENCE_THRESHOLD = 0.7;

interface OtherSpeciesGroup {
    label: string;
    commonName: string | null;
    scientificName: string | null;
    count: number;
    maxScore: number;
}

interface ReviewMomentPartition {
    focusMoments: FrameMoment[];
    otherConfidentMoments: FrameMoment[];
    otherSpecies: OtherSpeciesGroup[];
}

interface ReviewBirdPartition {
    focusBirds: BirdObservation[];
    confidentBystanders: BirdObservation[];
    excludedBirds: BirdObservation[];
    hasMixedCertainty: boolean;
}

interface CropViewport {
    x: number;
    y: number;
    width: number;
    height: number;
}

function normalizeSpeciesKey(value: string | null | undefined): string | null {
    const cleaned = String(value ?? '')
        .trim()
        .replace(/_/g, ' ')
        .replace(/\s+/g, ' ')
        .toLocaleLowerCase();
    return cleaned.length > 0 ? cleaned : null;
}

function effectiveBirdScore(bird: BirdObservation): number {
    if (bird.identity_source === 'visit' && typeof bird.identity_score === 'number') {
        return bird.identity_score;
    }
    return bird.classifier_score ?? 0;
}

/** Whether a visible counted bird still needs a person's eye in the review queue. */
export function isBirdUncertain(
    bird: BirdObservation,
    threshold: number = DEFAULT_REVIEW_CONFIDENCE_THRESHOLD
): boolean {
    if (bird.is_hidden) return false;
    if (isUnknownBird(bird)) return true;
    if (bird.manual_species) return false;
    return effectiveBirdScore(bird) < threshold;
}

/**
 * In Needs your call, a multi-bird capture often mixes one uncertain bird with confident
 * bystanders. Lead with what needs a decision and tuck confident bystanders out of the way.
 */
export function partitionCountedBirdsForReview(
    birds: readonly BirdObservation[],
    threshold: number = DEFAULT_REVIEW_CONFIDENCE_THRESHOLD
): ReviewBirdPartition {
    const visible = birds.filter((bird) => !bird.is_hidden);
    const excludedBirds = birds.filter((bird) => bird.is_hidden);
    const uncertain = visible.filter((bird) => isBirdUncertain(bird, threshold));
    const tracked = visible.filter((bird) => bird.tracked && !isBirdUncertain(bird, threshold));
    const confidentBystanders = visible.filter((bird) => !bird.tracked && !isBirdUncertain(bird, threshold));
    const hasMixedCertainty = uncertain.length > 0 && confidentBystanders.length > 0;

    if (!hasMixedCertainty) {
        return {
            focusBirds: visible,
            confidentBystanders: [],
            excludedBirds,
            hasMixedCertainty: false
        };
    }

    return {
        focusBirds: [...uncertain, ...tracked],
        confidentBystanders,
        excludedBirds,
        hasMixedCertainty: true
    };
}

/**
 * When a multi-bird capture has no tracked bird tying the visit name down and exactly one
 * visible bird is still unnamed (Unknown), naming the visit in Needs your call can safely
 * name that single uncertain bird too. Never guesses when two birds are unknown.
 */
export function singleUncertainBirdToSync(
    birds: readonly BirdObservation[],
    threshold: number = DEFAULT_REVIEW_CONFIDENCE_THRESHOLD
): BirdObservation | null {
    const visible = birds.filter((bird) => !bird.is_hidden);
    if (visible.length < 2) return null;
    if (visible.some((bird) => bird.tracked)) return null;
    const uncertain = visible.filter((bird) => isBirdUncertain(bird, threshold));
    if (uncertain.length !== 1) return null;
    const [target] = uncertain;
    if (!isUnknownBird(target) || target.manual_species) return null;
    return target;
}

/**
 * On a wide full-frame photograph of a multi-bird capture with exactly one uncertain bird
 * and at least one confident bystander, offer/lead with that uncertain bird's crop so the
 * reviewer does not have to hunt for a distant speck across the whole garden.
 */
export function shouldAutoFocusUncertainBird(
    photograph: SnapshotCandidate | null,
    birds: readonly BirdObservation[],
    threshold: number = DEFAULT_REVIEW_CONFIDENCE_THRESHOLD
): BirdObservation | null {
    if (!photograph || photograph.crop_box) return null;
    const visible = birds.filter((bird) => !bird.is_hidden);
    if (visible.length < 2) return null;
    const uncertain = visible.filter((bird) => isBirdUncertain(bird, threshold));
    const confident = visible.filter((bird) => !isBirdUncertain(bird, threshold));
    if (uncertain.length !== 1 || confident.length === 0) return null;
    return uncertain[0];
}

function detectionSubjectKeys(detection: Detection | null): Set<string> {
    const keys = new Set<string>();
    if (!detection) return keys;
    for (const raw of [
        detection.category_name,
        detection.scientific_name,
        detection.common_name,
        detection.display_name
    ]) {
        const key = normalizeSpeciesKey(raw);
        if (key && !isUnknownBirdLabel(key)) keys.add(key);
    }
    return keys;
}

function momentReadKeys(moment: FrameMoment): string[] {
    if (!moment.read) return [];
    const keys: string[] = [];
    for (const raw of [moment.read.label, moment.read.commonName, moment.read.scientificName]) {
        const key = normalizeSpeciesKey(raw);
        if (key && !keys.includes(key)) keys.push(key);
    }
    return keys;
}

/**
 * Splits a multi-bird visit's frame strip into moments relevant to the review decision
 * and confident crops of *other* bystander species (e.g. a 90% Jackdaw next to an uncertain bird).
 * Single-bird captures and whole scenes are never hidden.
 */
export function partitionReviewMoments(
    moments: readonly FrameMoment[],
    detection: Detection | null,
    currentKey: string | null,
    threshold: number = DEFAULT_REVIEW_CONFIDENCE_THRESHOLD
): ReviewMomentPartition {
    const subjectKeys = detectionSubjectKeys(detection);
    const focus: FrameMoment[] = [];
    const otherConfident: FrameMoment[] = [];

    for (const moment of moments) {
        const isSavedPhoto = currentKey !== null && moment.key === currentKey;
        const read = moment.read;
        const readKeys = momentReadKeys(moment);
        const readIsKnown = readKeys.length > 0 && readKeys.every((key) => !isUnknownBirdLabel(key));
        const matchesSubject = readKeys.some((key) => subjectKeys.has(key));
        const isConfidentOtherCrop =
            moment.choice === 'crop' &&
            !isSavedPhoto &&
            read !== null &&
            read.score !== null &&
            read.score >= threshold &&
            readIsKnown &&
            !matchesSubject;

        if (isConfidentOtherCrop) {
            otherConfident.push(moment);
        } else {
            focus.push(moment);
        }
    }

    // Never hide everything: if nothing stayed in focus, show the complete strip.
    if (focus.length === 0) {
        return {
            focusMoments: moments.map((moment, index) => ({ ...moment, position: index + 1 })),
            otherConfidentMoments: [],
            otherSpecies: []
        };
    }

    const groups = new Map<string, OtherSpeciesGroup>();
    for (const moment of otherConfident) {
        if (!moment.read) continue;
        const groupKey =
            normalizeSpeciesKey(moment.read.scientificName) ??
            normalizeSpeciesKey(moment.read.commonName) ??
            normalizeSpeciesKey(moment.read.label);
        if (!groupKey) continue;
        const score = moment.read.score ?? 0;
        const existing = groups.get(groupKey);
        if (existing) {
            existing.count += 1;
            existing.maxScore = Math.max(existing.maxScore, score);
            if (!existing.commonName && moment.read.commonName) existing.commonName = moment.read.commonName;
            if (!existing.scientificName && moment.read.scientificName) existing.scientificName = moment.read.scientificName;
        } else {
            groups.set(groupKey, {
                label: moment.read.label,
                commonName: moment.read.commonName ?? null,
                scientificName: moment.read.scientificName ?? null,
                count: 1,
                maxScore: score
            });
        }
    }

    const otherSpecies = [...groups.values()].sort((a, b) => b.count - a.count || b.maxScore - a.maxScore);
    return {
        focusMoments: focus.map((moment, index) => ({ ...moment, position: index + 1 })),
        otherConfidentMoments: otherConfident,
        otherSpecies
    };
}

function boxIoU(a: readonly number[], b: readonly number[]): number {
    if (a.length < 4 || b.length < 4) return 0;
    const ix = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0]));
    const iy = Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
    const inter = ix * iy;
    if (inter <= 0) return 0;
    const areaA = Math.max(0, a[2] - a[0]) * Math.max(0, a[3] - a[1]);
    const areaB = Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]);
    const union = areaA + areaB - inter;
    return union > 0 ? inter / union : 0;
}

/** Find a stored crop candidate image for a counted bird when one exists. */
export function findMatchingCropCandidateForBird(
    bird: BirdObservation,
    candidates: readonly SnapshotCandidate[]
): SnapshotCandidate | null {
    const usable = candidates.filter(
        (candidate) =>
            !candidate.photo_hidden &&
            candidate.source_mode !== 'full_frame' &&
            candidate.source_mode !== 'hq_candidate_full_frame' &&
            candidate.source_mode !== 'model_observation' &&
            Boolean(candidate.image_url)
    );
    const exact = usable.find((candidate) => candidate.candidate_id === bird.candidate_id);
    if (exact) return exact;

    let best: { candidate: SnapshotCandidate; iou: number } | null = null;
    for (const candidate of usable) {
        if (candidate.clip_variant !== bird.clip_variant || candidate.frame_index !== bird.frame_index) continue;
        if (!candidate.crop_box) continue;
        const iou = boxIoU(bird.crop_box, candidate.crop_box);
        if (iou >= 0.5 && (!best || iou > best.iou)) {
            best = { candidate, iou };
        }
    }
    return best?.candidate ?? null;
}

/**
 * Compute a readable padded crop window around a bird's pixel box inside its full-resolution scene.
 * Keeps a balanced square-ish aspect with surroundings so small birds are clear without over-zooming.
 */
export function computeCropViewport(
    cropBox: readonly number[] | null | undefined,
    natural: SourceSize | null | undefined,
    paddingFactor = 2.4,
    minSpan = 180
): CropViewport | null {
    if (!cropBox || cropBox.length < 4 || !natural || natural.width <= 0 || natural.height <= 0) return null;
    const [left, top, right, bottom] = cropBox;
    if (![left, top, right, bottom].every(Number.isFinite) || right <= left || bottom <= top) return null;

    const boxW = right - left;
    const boxH = bottom - top;
    const cx = (left + right) / 2;
    const cy = (top + bottom) / 2;

    const desiredSpan = Math.max(Math.max(boxW, boxH) * paddingFactor, minSpan);
    const width = Math.min(natural.width, desiredSpan * (4 / 3));
    const height = Math.min(natural.height, desiredSpan);

    const x = Math.min(Math.max(0, cx - width / 2), Math.max(0, natural.width - width));
    const y = Math.min(Math.max(0, cy - height / 2), Math.max(0, natural.height - height));
    return { x, y, width, height };
}
