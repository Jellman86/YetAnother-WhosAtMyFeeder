import type { GardenCapture } from '../api/garden';
import type { DetectionVisit } from '../api/visits';
import { heardWindow } from './heard-timeline';

/**
 * Where Garden captures sit in the Explorer.
 *
 * They are stored apart from birds, so no total, export or notification can count an animal by
 * accident, and the Explorer reads both and places each capture between the visits it fell
 * between. Visits stay in the order the server gave them; a capture never moves one.
 */

export type ExplorerSubjects = 'birds' | 'garden' | 'all';

export interface GardenEntryView {
    /** The species name, only from an identification that has not been discarded. */
    name: string | null;
    nameState: 'confirmed' | 'automatic' | 'suggested' | 'none';
    /** The identification model's score, never the detector's. */
    score: number | null;
    /** What still needs a person: that an animal is there, or which one it is. */
    review: 'presence' | 'species' | null;
}

export function gardenEntryView(capture: GardenCapture): GardenEntryView {
    const identification = capture.identification;
    const standing =
        identification && identification.outcome === 'suggestion' && identification.review !== 'dismissed' && identification.name
            ? identification
            : null;
    const nameState: GardenEntryView['nameState'] = !standing
        ? 'none'
        : standing.review === 'accepted'
          ? standing.automatic
              ? 'automatic'
              : 'confirmed'
          : 'suggested';
    return {
        name: standing?.name ?? null,
        nameState,
        score: standing?.score ?? null,
        review: capture.status === 'pending' ? 'presence' : nameState === 'suggested' ? 'species' : null
    };
}

export interface GardenFilterState {
    speciesFilter: string;
    favoritesOnly: boolean;
    showHidden: boolean;
    multipleSpeciesOnly: boolean;
    audioConfirmedOnly: boolean;
    sortOrder: 'newest' | 'oldest' | 'confidence';
    groupVisits: boolean;
    selectionMode: boolean;
}

export type GardenBlocker = 'bird_filter' | 'confidence_sort' | 'ungrouped' | 'selection' | 'bird_filter_ignored';

function birdOnlyFilter(state: GardenFilterState): boolean {
    return Boolean(state.speciesFilter || state.favoritesOnly || state.showHidden || state.multipleSpeciesOnly || state.audioConfirmedOnly);
}

/**
 * Why Garden captures are not shown, or are shown without some filters.
 *
 * A capture has no bird species, favourite, hidden state or matching call, so a filter about
 * those cannot apply to it. Beside birds the captures step aside and the page says why; on their
 * own they are shown and the page says which filters were left out.
 */
export function gardenBlocker(subjects: ExplorerSubjects, state: GardenFilterState): GardenBlocker | null {
    if (subjects === 'birds') return null;
    if (subjects === 'garden') return birdOnlyFilter(state) || state.sortOrder === 'confidence' ? 'bird_filter_ignored' : null;
    if (state.selectionMode) return 'selection';
    if (!state.groupVisits) return 'ungrouped';
    if (birdOnlyFilter(state)) return 'bird_filter';
    if (state.sortOrder === 'confidence') return 'confidence_sort';
    return null;
}

export type PlacedEntry<T> = T | { kind: 'garden'; capture: GardenCapture };

/** Merges captures into entries already in display order, by the time each one shows. */
export function placeGardenCaptures<T>(
    entries: T[],
    timeOf: (entry: T) => number,
    captures: GardenCapture[],
    sort: 'newest' | 'oldest'
): PlacedEntry<T>[] {
    const newest = sort === 'newest';
    const at = (capture: GardenCapture): number => Date.parse(capture.observed_at);
    const pending = [...captures].sort((a, b) => (newest ? at(b) - at(a) : at(a) - at(b)));
    const placed: PlacedEntry<T>[] = [];
    let next = 0;
    for (const entry of entries) {
        const time = timeOf(entry);
        while (next < pending.length && (newest ? at(pending[next]) > time : at(pending[next]) < time)) {
            placed.push({ kind: 'garden', capture: pending[next++] });
        }
        placed.push(entry);
    }
    for (; next < pending.length; next++) placed.push({ kind: 'garden', capture: pending[next] });
    return placed;
}

/**
 * The span of Garden captures a page of visits owns: the same span as its heard calls, so no
 * capture shows on two pages. A filter with no bird visits at all still shows its animals.
 */
export function gardenWindow(input: {
    visits: DetectionVisit[];
    sort: 'newest' | 'oldest';
    previous: DetectionVisit | null;
    hasNextPage: boolean;
    birdTotal: number;
    rangeStart: Date | null;
    rangeEnd: Date | null;
    now: Date;
}): { start: Date | null; end: Date } | null {
    if (input.visits.length) return heardWindow(input);
    if (input.birdTotal > 0) return null;
    return { start: input.rangeStart, end: input.rangeEnd && input.rangeEnd < input.now ? input.rangeEnd : input.now };
}

type Translate = (key: string, fallback: string, values?: Record<string, string>) => string;

/** The title and one state line an Explorer entry shows, so a row, a card and a record agree. */
export function gardenEntryText(capture: GardenCapture, view: GardenEntryView, t: Translate): { title: string; state: string } {
    const title = view.name
        ?? (capture.status === 'pending'
            ? t('garden.explorer.possible_animal', 'Possible animal')
            : t('garden.explorer.unnamed_animal', 'Animal, not named'));
    if (view.review === 'presence') return { title, state: t('garden.explorer.state_presence', 'Needs review: is an animal there?') };
    if (view.review === 'species') return { title, state: t('garden.explorer.state_species', 'Needs review: suggested species') };
    if (view.nameState === 'automatic') return { title, state: t('garden.explorer.state_automatic', 'Named automatically') };
    if (view.nameState === 'confirmed') return { title, state: t('garden.explorer.state_confirmed', 'Species confirmed by you') };
    return { title, state: t('garden.explorer.state_unnamed', 'Animal confirmed, species not named') };
}
