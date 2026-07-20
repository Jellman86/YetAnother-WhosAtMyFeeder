import type { Detection } from './api';

export type DetectionClassificationSource = 'snapshot' | 'manual' | 'video';
export type ClassificationInputKind = 'video_crop' | 'video_full' | 'snapshot_crop' | 'snapshot_full' | 'upstream' | 'unknown';

const VIDEO_CROP_SOURCES = new Set(['frigate_hint_crop', 'model_crop', 'provided_crop']);
const VIDEO_FULL_SOURCES = new Set(['full_frame']);
const SNAPSHOT_CROP_SOURCES = new Set([
    'frigate_snapshot_cropped',
    'high_quality_bird_crop',
    'snapshot_frigate_hint_crop',
    'snapshot_model_crop',
    'hq_candidate_frigate_hint_crop',
    'hq_candidate_model_crop'
]);
const SNAPSHOT_FULL_SOURCES = new Set([
    'cached_snapshot_unknown',
    'frigate_snapshot',
    'frigate_snapshot_uncropped',
    'frigate_recording_frame',
    'frigate_thumbnail',
    'high_quality_snapshot',
    'hq_candidate_full_frame'
]);
const UPSTREAM_SOURCES = new Set(['frigate_sublabel']);

function normalizeSourceLabel(value: unknown): string {
    if (typeof value !== 'string') return '';
    let normalized = value.trim().toLowerCase();
    if (!normalized) return '';

    // Mirror the backend's collapsed-label behavior for variant suffixes.
    let next = normalized.replace(/\s*\([^()]*\)\s*$/u, '').trim();
    while (next && next !== normalized) {
        normalized = next;
        next = normalized.replace(/\s*\([^()]*\)\s*$/u, '').trim();
    }
    return normalized;
}

export function getDetectionClassificationSource(detection: Detection): DetectionClassificationSource {
    const currentCategory = normalizeSourceLabel(detection.category_name);
    const videoLabel = normalizeSourceLabel(detection.video_classification_label);
    const videoCompleted = String(detection.video_classification_status ?? '').trim().toLowerCase() === 'completed';

    const inputKind = getClassificationInputKind(detection.video_classification_input_source);
    const videoEvidence = inputKind === 'video_crop' || inputKind === 'video_full' || inputKind === 'unknown';

    if (videoCompleted && videoEvidence && currentCategory && videoLabel && currentCategory === videoLabel) {
        return 'video';
    }

    if (detection.manual_tagged) {
        return 'manual';
    }

    return 'snapshot';
}

export function getClassificationInputKind(value: unknown): ClassificationInputKind {
    const source = typeof value === 'string' ? value.trim().toLowerCase() : '';
    if (VIDEO_CROP_SOURCES.has(source)) return 'video_crop';
    if (VIDEO_FULL_SOURCES.has(source)) return 'video_full';
    if (SNAPSHOT_CROP_SOURCES.has(source)) return 'snapshot_crop';
    if (SNAPSHOT_FULL_SOURCES.has(source)) return 'snapshot_full';
    if (UPSTREAM_SOURCES.has(source)) return 'upstream';
    return 'unknown';
}
