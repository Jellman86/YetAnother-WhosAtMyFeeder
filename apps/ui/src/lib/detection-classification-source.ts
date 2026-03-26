import type { Detection } from './api';

export type DetectionClassificationSource = 'snapshot' | 'manual' | 'video';

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

    if (videoCompleted && currentCategory && videoLabel && currentCategory === videoLabel) {
        return 'video';
    }

    if (detection.manual_tagged) {
        return 'manual';
    }

    return 'snapshot';
}
