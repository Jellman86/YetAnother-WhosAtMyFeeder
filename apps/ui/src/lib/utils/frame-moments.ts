import type { SnapshotCandidate } from '../api';

/**
 * A moment of the visit that can be the record's photograph.
 *
 * The classifier produces several candidates per frame: the whole scene, a crop guided by the
 * camera's box, a crop from the bird detector. Which subsystem produced a picture is the app's
 * own plumbing (#256). A person choosing the most representative photograph sees one thumbnail
 * per moment; the framings of that moment fold into it, the closest one shown.
 */
export interface FrameMoment {
    /** Stable identity within the strip. */
    key: string;
    /** 1-based place in the strip, in time order. */
    position: number;
    frameIndex: number | null;
    offsetSeconds: number | null;
    /** The framing closest on the bird, if the moment has one. */
    crop: SnapshotCandidate | null;
    /** The uncropped scene for the same moment, if the moment has one. */
    whole: SnapshotCandidate | null;
    /** What the model read in this moment, from the candidate it was most sure about. */
    read: { label: string; score: number | null } | null;
    /** The camera's own saved snapshot, which has no candidate record. */
    asRecorded: boolean;
}

export const AS_RECORDED_KEY = 'as-recorded';

const WHOLE_SCENE_MODES = new Set(['full_frame', 'hq_candidate_full_frame']);
const CROP_PREFERENCE = ['model_crop', 'frigate_hint_crop'];

function isWholeSceneCandidate(candidate: SnapshotCandidate): boolean {
    return WHOLE_SCENE_MODES.has(candidate.source_mode);
}

function pickCrop(candidates: SnapshotCandidate[]): SnapshotCandidate | null {
    const crops = candidates.filter((candidate) => !isWholeSceneCandidate(candidate));
    if (crops.length === 0) return null;
    for (const mode of CROP_PREFERENCE) {
        const preferred = crops
            .filter((candidate) => candidate.source_mode === mode)
            .sort((a, b) => b.ranking_score - a.ranking_score)[0];
        if (preferred) return preferred;
    }
    return [...crops].sort((a, b) => b.ranking_score - a.ranking_score)[0] ?? null;
}

function pickRead(candidates: SnapshotCandidate[]): FrameMoment['read'] {
    const read = candidates
        .filter((candidate) => (candidate.classifier_label ?? '').trim() !== '')
        .sort((a, b) => (b.classifier_score ?? -1) - (a.classifier_score ?? -1))[0];
    if (!read?.classifier_label) return null;
    return { label: read.classifier_label, score: read.classifier_score ?? null };
}

/**
 * Fold candidates into moments, oldest first. The camera's own snapshot, when it is still
 * available, leads the strip: it is the one picture that exists before any analysis ran.
 */
export function groupCandidatesIntoMoments(
    candidates: SnapshotCandidate[],
    options: { asRecordedAvailable?: boolean } = {}
): FrameMoment[] {
    const groups = new Map<string, SnapshotCandidate[]>();
    for (const candidate of candidates) {
        const key = `${candidate.clip_variant}:${candidate.frame_index}`;
        const group = groups.get(key);
        if (group) group.push(candidate);
        else groups.set(key, [candidate]);
    }

    const moments: FrameMoment[] = [];
    if (options.asRecordedAvailable) {
        moments.push({
            key: AS_RECORDED_KEY,
            position: 0,
            frameIndex: null,
            offsetSeconds: null,
            crop: null,
            whole: null,
            read: null,
            asRecorded: true
        });
    }

    const grouped = [...groups.entries()].map(([key, group]) => {
        const offsets = group
            .map((candidate) => candidate.frame_offset_seconds)
            .filter((value): value is number => typeof value === 'number');
        return {
            key,
            position: 0,
            frameIndex: group[0]?.frame_index ?? null,
            offsetSeconds: offsets.length > 0 ? Math.min(...offsets) : null,
            crop: pickCrop(group),
            whole: group.find(isWholeSceneCandidate) ?? null,
            read: pickRead(group),
            asRecorded: false
        } satisfies FrameMoment;
    });
    grouped.sort((a, b) => {
        const byOffset = (a.offsetSeconds ?? Number.POSITIVE_INFINITY) - (b.offsetSeconds ?? Number.POSITIVE_INFINITY);
        if (byOffset !== 0 && Number.isFinite(byOffset)) return byOffset;
        return (a.frameIndex ?? 0) - (b.frameIndex ?? 0);
    });
    moments.push(...grouped);

    return moments.map((moment, index) => ({ ...moment, position: index + 1 }));
}

/** The candidate a moment stands for: close on the bird when it can be, the whole scene otherwise. */
export function preferredCandidate(moment: FrameMoment): SnapshotCandidate | null {
    return moment.crop ?? moment.whole;
}

export function momentThumbnailUrl(moment: FrameMoment): string | null {
    const candidate = preferredCandidate(moment);
    return candidate?.thumbnail_url ?? candidate?.image_url ?? null;
}

export function momentImageUrl(moment: FrameMoment): string | null {
    const candidate = preferredCandidate(moment);
    return candidate?.image_url ?? candidate?.thumbnail_url ?? null;
}

/** Which moment the record currently uses as its photograph, or null when none matches. */
export function currentMoment(
    moments: FrameMoment[],
    currentCandidateId: string | null,
    currentSource: string | null
): FrameMoment | null {
    if (currentSource === 'frigate_snapshot') {
        return moments.find((moment) => moment.asRecorded) ?? null;
    }
    if (!currentCandidateId) return null;
    return (
        moments.find(
            (moment) =>
                moment.crop?.candidate_id === currentCandidateId || moment.whole?.candidate_id === currentCandidateId
        ) ?? null
    );
}

/** "0:07" for a clip offset. Offsets under a second read as 0:00. */
export function formatOffset(seconds: number | null): string | null {
    if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return null;
    const whole = Math.floor(seconds);
    const minutes = Math.floor(whole / 60);
    const rest = whole % 60;
    return `${minutes}:${String(rest).padStart(2, '0')}`;
}

export interface OutlineBox {
    left: number;
    top: number;
    width: number;
    height: number;
}

/**
 * Where the crop sits on a whole-scene image drawn with `object-fit: contain`.
 *
 * `cropBox` is the classifier's pixel box on the full frame (left, top, right, bottom). The
 * result is in container pixels, accounting for the letterbox `contain` adds, so an outline
 * positioned with it lands on the bird and not on the bars.
 */
export function wholeSceneOutline(
    cropBox: ReadonlyArray<number> | null | undefined,
    natural: { width: number; height: number },
    container: { width: number; height: number }
): OutlineBox | null {
    if (!cropBox || cropBox.length < 4) return null;
    const [left, top, right, bottom] = cropBox;
    if (natural.width <= 0 || natural.height <= 0 || container.width <= 0 || container.height <= 0) return null;
    if (right <= left || bottom <= top) return null;

    const scale = Math.min(container.width / natural.width, container.height / natural.height);
    const drawnWidth = natural.width * scale;
    const drawnHeight = natural.height * scale;
    const offsetX = (container.width - drawnWidth) / 2;
    const offsetY = (container.height - drawnHeight) / 2;

    const clampX = (value: number) => Math.min(Math.max(value, 0), natural.width);
    const clampY = (value: number) => Math.min(Math.max(value, 0), natural.height);
    const l = clampX(left);
    const t = clampY(top);
    const r = clampX(right);
    const b = clampY(bottom);
    if (r <= l || b <= t) return null;

    return {
        left: offsetX + l * scale,
        top: offsetY + t * scale,
        width: (r - l) * scale,
        height: (b - t) * scale
    };
}
