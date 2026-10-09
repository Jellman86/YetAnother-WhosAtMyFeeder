import type { BackfillJobStatus } from '../api/backfill';

export type BackfillTerminalKind = 'detections' | 'weather';

const KIND_LABELS: Record<BackfillTerminalKind, string> = {
    detections: 'Detection backfill',
    weather: 'Weather backfill',
};

export function formatTerminalBackfillMessage(
    kind: BackfillTerminalKind,
    message: string | null | undefined,
    fallbackText: string
): string {
    const normalized = typeof message === 'string' ? message.trim() : '';
    if (!normalized) return fallbackText;
    return `${KIND_LABELS[kind]}: ${normalized}`;
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
