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
