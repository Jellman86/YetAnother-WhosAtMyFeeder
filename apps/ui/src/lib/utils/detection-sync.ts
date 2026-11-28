import type { Detection } from '../api';

/** The fields a shown detection draws from, so a live update that changes none of them changes nothing. */
function detectionSyncSignature(d: Detection): string {
    const asText = (value: unknown) => (value === null || value === undefined ? '' : String(value));
    const asNumber = (value: unknown) => {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? String(parsed) : '';
    };
    const asFlag = (value: unknown) => (value ? '1' : '0');
    return [
        asText(d.frigate_event),
        asText(d.display_name),
        asNumber(d.score),
        asFlag(d.manual_tagged),
        asFlag(d.is_hidden),
        asFlag(d.is_favorite),
        asText(d.video_classification_status),
        asText(d.video_classification_label),
        asNumber(d.video_classification_score),
        asText(d.ai_analysis),
        asText(d.ai_analysis_timestamp),
        JSON.stringify(d.bird_summary ?? null)
    ].join('|');
}

/**
 * `current` with the fields a live update defined, or `current` itself when nothing shown changed,
 * so a caller can compare identities and skip a redraw.
 */
export function withLiveFields(current: Detection, patch: Partial<Detection> | undefined): Detection {
    if (!patch) return current;
    const defined = Object.fromEntries(Object.entries(patch).filter(([, value]) => value !== undefined)) as Partial<Detection>;
    const merged = { ...current, ...defined } as Detection;
    return detectionSyncSignature(merged) === detectionSyncSignature(current) ? current : merged;
}
