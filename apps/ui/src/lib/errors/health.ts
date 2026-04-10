export interface VideoClassifierCardState {
    status: string;
    summary: string;
    pending: number;
    active: number;
    failureCount: number;
    openUntil: string;
}

function asNumber(value: unknown): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
}

function asText(value: unknown, fallback = ''): string {
    if (typeof value !== 'string') return fallback;
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : fallback;
}

function normalizeStatus(value: unknown): string {
    const normalized = asText(value).toLowerCase();
    return normalized;
}

export function getVideoClassifierCardState(health: Record<string, any> | null | undefined): VideoClassifierCardState {
    const video = health?.video_classifier ?? {};
    const pending = asNumber(video.pending);
    const active = asNumber(video.active);
    const failureCount = asNumber(video.failure_count);
    const circuitOpen = Boolean(video.circuit_open);
    const explicitStatus = normalizeStatus(video.status);

    let status = explicitStatus;
    if (circuitOpen) {
        status = 'open';
    } else if (!status || status === 'unknown') {
        if (active > 0) {
            status = 'processing';
        } else if (pending > 0) {
            status = 'queued';
        } else {
            status = 'idle';
        }
    }

    const openUntil = asText(video.open_until, 'Closed') || 'Closed';
    const summary = circuitOpen
        ? `Video circuit breaker is open with ${failureCount.toLocaleString()} recent failures.`
        : `${pending.toLocaleString()} queued, ${active.toLocaleString()} active video jobs.`;

    return {
        status,
        summary,
        pending,
        active,
        failureCount,
        openUntil,
    };
}
