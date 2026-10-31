export const MAX_MANUAL_IMAGE_BYTES = 25 * 1024 * 1024;
export const MAX_MANUAL_VIDEO_BYTES = 250 * 1024 * 1024;

const MANUAL_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const MANUAL_VIDEO_TYPES = new Set(['video/mp4', 'video/quicktime', 'video/webm']);

type ManualObservationUploadRejection =
    | 'unsupported_type'
    | 'image_too_large'
    | 'video_too_large';

export type ManualObservationUploadValidation =
    | { ok: true }
    | { ok: false; reason: ManualObservationUploadRejection };

interface ManualObservationUploadCandidate {
    type: string;
    size: number;
}

export function validateManualObservationUpload(
    file: ManualObservationUploadCandidate
): ManualObservationUploadValidation {
    if (MANUAL_IMAGE_TYPES.has(file.type)) {
        return file.size <= MAX_MANUAL_IMAGE_BYTES
            ? { ok: true }
            : { ok: false, reason: 'image_too_large' };
    }
    if (MANUAL_VIDEO_TYPES.has(file.type)) {
        return file.size <= MAX_MANUAL_VIDEO_BYTES
            ? { ok: true }
            : { ok: false, reason: 'video_too_large' };
    }
    return { ok: false, reason: 'unsupported_type' };
}

interface NamedPrediction {
    label: string;
    scientific_name?: string | null;
    common_name?: string | null;
}

function speciesKey(value: string | null | undefined): string {
    return (value ?? '').replaceAll('_', ' ').split(/\s+/).filter(Boolean).join(' ').toLocaleLowerCase();
}

/**
 * The suggestion a typed or chosen species refers to, whichever of its names was used. The server
 * applies the same rule when it picks the saved photo, so the page shows the photo that will be kept.
 */
export function findPredictionForSpecies<T extends NamedPrediction>(predictions: readonly T[], species: string): T | null {
    const wanted = speciesKey(species);
    if (!wanted) return null;
    return predictions.find((prediction) =>
        [prediction.label, prediction.scientific_name, prediction.common_name].some((name) => speciesKey(name) === wanted)
    ) ?? null;
}

/** "0:04", "1:12": where in a video a frame sits, for people rather than timecode. */
export function formatVideoOffset(seconds: number): string {
    const whole = Math.max(0, Math.floor(seconds));
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

/**
 * A UTC instant as a `datetime-local` value in the browser's own zone, to the second, so a time read
 * from the file is shown as the wall-clock time it was taken and saved back unchanged. Empty when the
 * value is not a time.
 */
export function toDateTimeLocalValue(iso: string | null | undefined): string {
    const moment = iso ? new Date(iso) : null;
    if (!moment || Number.isNaN(moment.getTime())) return '';
    const pad = (value: number): string => String(value).padStart(2, '0');
    return `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())}`
        + `T${pad(moment.getHours())}:${pad(moment.getMinutes())}:${pad(moment.getSeconds())}`;
}

export type DuplicateUpload =
    | { kind: 'saved'; eventId: string }
    | { kind: 'draft'; draftId: string };

const DRAFT_ID = /^[a-f0-9]{32}$/;
const MANUAL_EVENT_ID = /^manual_[a-f0-9]{32}$/;

/**
 * Where an upload the server already holds can be found, read from its 409 body. The body is
 * untrusted, so only identifiers of the exact shape the server issues are accepted.
 */
export function readDuplicateUpload(payload: unknown): DuplicateUpload | null {
    if (!payload || typeof payload !== 'object') return null;
    const detail = (payload as { detail?: unknown }).detail;
    if (!detail || typeof detail !== 'object') return null;
    const { draft_id: draftId, event_id: eventId } = detail as { draft_id?: unknown; event_id?: unknown };
    if (typeof eventId === 'string' && MANUAL_EVENT_ID.test(eventId)) return { kind: 'saved', eventId };
    if (typeof draftId === 'string' && DRAFT_ID.test(draftId)) return { kind: 'draft', draftId };
    return null;
}
