import { get } from 'svelte/store';
import { _ } from 'svelte-i18n';
import type { BackfillJobStatus } from '../api/backfill';

export type BackfillTerminalKind = 'detections' | 'weather';

const KIND_LABELS: Record<BackfillTerminalKind, { key: string; fallback: string }> = {
    detections: { key: 'jobs.kind_backfill', fallback: 'Import of missed visits' },
    weather: { key: 'jobs.kind_weather_backfill', fallback: 'Missing weather' },
};

/** The job's name in the reader's language, as the jobs list names it. */
function kindLabel(kind: BackfillTerminalKind): string {
    const { key, fallback } = KIND_LABELS[kind];
    try {
        return get(_)(key, { default: fallback });
    } catch {
        return fallback;
    }
}

export function formatTerminalBackfillMessage(
    kind: BackfillTerminalKind,
    message: string | null | undefined,
    fallbackText: string
): string {
    const normalized = typeof message === 'string' ? message.trim() : '';
    if (!normalized) return fallbackText;
    return `${kindLabel(kind)}: ${normalized}`;
}

export function isBackfillTerminalTransition(
    previous: Pick<BackfillJobStatus, 'id' | 'status'> | null,
    current: Pick<BackfillJobStatus, 'id' | 'status'> | null
): boolean {
    return !!current?.id
        && previous?.id === current.id
        && previous.status === 'running'
        && (current.status === 'completed' || current.status === 'failed');
}
