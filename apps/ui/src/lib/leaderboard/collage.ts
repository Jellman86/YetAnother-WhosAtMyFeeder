import type { Detection, LeaderboardSpan } from '../api';
import { groupDetectionsIntoVisits } from '../utils/visit-grouping';

export interface CollageDateQuery {
    startDate?: string;
    endDate?: string;
}

interface CollageSelectionOptions {
    windowStart?: string | null;
    windowEnd?: string | null;
    maxPhotos?: number;
}

export interface CollageSlotAdvance {
    slots: string[];
    nextTile: number;
}

function parsedTimestamp(value: string): number | null {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : parsed;
}

export function collageDateQuery(
    span: LeaderboardSpan,
    windowStart: string | null,
    windowEnd: string | null
): CollageDateQuery | null {
    if (span === 'all') return {};

    const start = windowStart ? parsedTimestamp(windowStart) : null;
    const end = windowEnd ? parsedTimestamp(windowEnd) : null;
    if (start === null || end === null || start > end) return null;

    return {
        startDate: new Date(start).toISOString().slice(0, 10),
        endDate: new Date(end).toISOString().slice(0, 10)
    };
}

function evenlySpaced<T>(items: T[], limit: number): T[] {
    if (items.length <= limit) return items;
    if (limit <= 1) return items.slice(0, Math.max(0, limit));

    return Array.from({ length: limit }, (_unused, index) => {
        const sourceIndex = Math.round((index * (items.length - 1)) / (limit - 1));
        return items[sourceIndex];
    });
}

/**
 * Select representative feeder photographs from real visits. Grouping is performed
 * per camera so simultaneous approaches never collapse into one visit.
 */
export function selectCollagePhotos(
    events: readonly Detection[],
    {
        windowStart = null,
        windowEnd = null,
        maxPhotos = 12
    }: CollageSelectionOptions = {}
): Detection[] {
    const start = windowStart ? parsedTimestamp(windowStart) : null;
    const end = windowEnd ? parsedTimestamp(windowEnd) : null;
    const uniqueEvents = new Map<string, Detection>();

    for (const event of events) {
        if (event.has_snapshot === false || uniqueEvents.has(event.frigate_event)) continue;
        const at = parsedTimestamp(event.detection_time);
        if (start !== null && (at === null || at < start)) continue;
        if (end !== null && (at === null || at > end)) continue;
        uniqueEvents.set(event.frigate_event, event);
    }

    const byCamera = new Map<string, Detection[]>();
    for (const event of uniqueEvents.values()) {
        const cameraEvents = byCamera.get(event.camera_name) ?? [];
        cameraEvents.push(event);
        byCamera.set(event.camera_name, cameraEvents);
    }

    const visits = [...byCamera.values()]
        .flatMap((cameraEvents) =>
            groupDetectionsIntoVisits(cameraEvents, { reviewThreshold: null })
        )
        .sort((left, right) => {
            const leftAt = parsedTimestamp(left.endTime) ?? 0;
            const rightAt = parsedTimestamp(right.endTime) ?? 0;
            return rightAt - leftAt;
        });

    return evenlySpaced(
        visits.map((visit) => visit.best),
        Math.max(0, maxPhotos)
    );
}

export function advanceCollageSlots(
    slots: readonly string[],
    available: readonly string[],
    nextTile: number
): CollageSlotAdvance {
    if (slots.length === 0 || available.length <= slots.length) {
        return { slots: [...slots], nextTile };
    }

    const shown = new Set(slots);
    const lastShownIndex = Math.max(...slots.map((slot) => available.indexOf(slot)));
    let candidateIndex = (lastShownIndex + 1) % available.length;
    for (let step = 0; step < available.length && shown.has(available[candidateIndex]); step++) {
        candidateIndex = (candidateIndex + 1) % available.length;
    }

    const candidate = available[candidateIndex];
    if (!candidate || shown.has(candidate)) return { slots: [...slots], nextTile };

    const tile = Math.min(Math.max(nextTile, 0), slots.length - 1);
    return {
        slots: slots.map((current, index) => (index === tile ? candidate : current)),
        nextTile: (tile + 1) % slots.length
    };
}
