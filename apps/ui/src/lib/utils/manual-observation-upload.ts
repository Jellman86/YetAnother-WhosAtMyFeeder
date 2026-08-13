export const MAX_MANUAL_IMAGE_BYTES = 25 * 1024 * 1024;
export const MAX_MANUAL_VIDEO_BYTES = 250 * 1024 * 1024;

const MANUAL_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const MANUAL_VIDEO_TYPES = new Set(['video/mp4', 'video/quicktime', 'video/webm']);

export type ManualObservationUploadRejection =
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
