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
