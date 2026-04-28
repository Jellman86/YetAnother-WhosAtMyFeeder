import type { Detection } from './api';

const UNKNOWN_LABELS = new Set(['unknown bird', 'unknown', 'background']);

function normalizeLabel(label: string | null | undefined): string {
    return (label || '').trim().toLowerCase();
}

function isUnknownLabel(label: string | null | undefined): boolean {
    return UNKNOWN_LABELS.has(normalizeLabel(label));
}

export function isVideoPromotionGated(detection: Detection | null | undefined): boolean {
    if (!detection) return false;
    if (detection.video_classification_status !== 'completed') return false;

    const videoLabel = normalizeLabel(detection.video_classification_label);
    if (!videoLabel || isUnknownLabel(videoLabel)) return false;
    if (detection.video_result_blocked) return false;

    const primaryIdentityLabels = [
        detection.display_name,
        detection.category_name,
        detection.scientific_name,
        detection.common_name
    ].map(normalizeLabel).filter(Boolean);

    return !primaryIdentityLabels.includes(videoLabel);
}
