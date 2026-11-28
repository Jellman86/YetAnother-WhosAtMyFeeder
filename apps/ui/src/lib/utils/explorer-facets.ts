import type { FetchEventFiltersOptions } from '../api/events';
import type { ExplorerDatePreset, ExplorerWindow } from './explorer-query';

/**
 * What the Explorer's facet counts are taken under (#1097).
 *
 * A count beside a filter states how many results choosing it would give, so it follows the
 * period, Visits or Captures, and the other filters in the rail. The server leaves each facet's
 * own choice out of its count, so the species list is never narrowed by the chosen species.
 */
export interface ExplorerFacetChoice {
    datePreset: ExplorerDatePreset;
    customStartDate: string;
    customEndDate: string;
    /** Visits are counted when the results show visits; selecting works on captures. */
    visits: boolean;
    species: string;
    taxon: number | null;
    camera: string;
    favoritesOnly: boolean;
    audioConfirmedOnly: boolean;
    multipleSpeciesOnly: boolean;
    ownerConfirmedOnly: boolean;
    onlyHidden: boolean;
}

/**
 * Whether the counts on screen describe the results on screen. `updating` keeps the last numbers in
 * view, marked as being read again, while the same filters and window are checked once more.
 */
export type ExplorerFacetCounts = 'current' | 'updating' | 'pending' | 'unavailable';

/** Names the filters a set of counts was read under; the window is keyed apart, by its bounds. */
export function explorerFacetKey(choice: ExplorerFacetChoice): string {
    const custom = choice.datePreset === 'custom' ? [choice.customStartDate, choice.customEndDate] : [];
    return JSON.stringify([
        choice.datePreset,
        ...custom,
        choice.visits ? 'visits' : 'captures',
        choice.species,
        choice.taxon,
        choice.camera,
        choice.favoritesOnly,
        choice.audioConfirmedOnly,
        choice.multipleSpeciesOnly,
        choice.ownerConfirmedOnly,
        choice.onlyHidden
    ]);
}

/** The filter read for a choice, over the window the results were read with. */
export function explorerFacetOptions(
    choice: ExplorerFacetChoice,
    window: ExplorerWindow['request']
): Omit<FetchEventFiltersOptions, 'forceRefresh'> {
    return {
        ...window,
        unit: choice.visits ? 'visits' : 'captures',
        species: choice.species || undefined,
        taxon: choice.taxon ?? undefined,
        camera: choice.camera || undefined,
        favoritesOnly: choice.favoritesOnly,
        audioConfirmedOnly: choice.audioConfirmedOnly,
        multipleSpeciesOnly: choice.multipleSpeciesOnly,
        ownerConfirmedOnly: choice.ownerConfirmedOnly,
        onlyHidden: choice.onlyHidden
    };
}

/**
 * One read of the counts: the filters and the window it was asked for, and how it went. Each read
 * replaces the last, so a retry or a refresh is waiting again rather than showing the old answer.
 */
export interface ExplorerFacetRead {
    generation: number;
    choice: string;
    window: string;
    visits: boolean;
    status: 'pending' | 'updating' | 'current' | 'failed';
}

/** A window as the counts' key: its actual bounds, so a period read again later is a new window. */
export function explorerFacetWindowKey(window: ExplorerWindow['request']): string {
    return JSON.stringify([window.startDate ?? null, window.endDate ?? null, window.startTime ?? null, window.endTime ?? null]);
}

/** Whether the results read now need their counts read for them: other filters, or another window. */
export function explorerFacetReadNeeded(read: ExplorerFacetRead | null, choice: string, window: string): boolean {
    return read === null || read.choice !== choice || read.window !== window;
}

/**
 * Whether the counts on screen describe the results: `shown` is the filters of the results read
 * last. Until a read for them has answered, the counts are waiting; a failed one has none to show.
 */
export function explorerFacetCounts(shown: string | null, read: ExplorerFacetRead | null): ExplorerFacetCounts {
    if (shown === null || read === null || read.choice !== shown || read.status === 'pending') return 'pending';
    if (read.status === 'updating') return 'updating';
    return read.status === 'failed' ? 'unavailable' : 'current';
}
