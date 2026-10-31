import type { GardenCapture } from '../api/garden';
import type { DetectionVisit } from '../api/visits';
import { heardWindow } from './heard-timeline';
import { groupGardenReview } from './garden-review-groups';

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
    if (capture.owner_identification && capture.status === 'confirmed') {
        return { name: capture.owner_identification.name, nameState: 'confirmed', score: null, review: null };
    }
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
        review: capture.status === 'pending'
            ? capture.automatic_check_overridden || ['naming_disabled', 'location_required', 'identity_unavailable'].includes(capture.automatic_check?.decision_reason ?? '') ? 'presence' : null
            : nameState === 'suggested' ? 'species' : null
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

type Translate = (key: string, fallback: string, values?: Record<string, string | number>) => string;

/** The title and one state line an Explorer entry shows, so a row, a card and a record agree. */
/**
 * The line under a Garden row's name, as a bird row's: a settled animal shows its scientific
 * name; the state is said in words only while the entry needs a person or has no name.
 */
export function gardenRowDetail(capture: GardenCapture, view: GardenEntryView): { scientific: string | null; showState: boolean } {
    const settled = capture.status === 'confirmed' && view.review === null && (view.nameState === 'automatic' || view.nameState === 'confirmed');
    const scientific = settled ? capture.scientific_name ?? null : null;
    return { scientific, showState: scientific === null };
}

/** Who is reading: only the owner confirmed anything, so only the owner is told "by you". */
export type GardenViewer = 'owner' | 'visitor';

export function gardenEntryText(capture: GardenCapture, view: GardenEntryView, t: Translate, viewer: GardenViewer): { title: string; state: string } {
    if (capture.status === 'dismissed') {
        return {
            title: t('garden.explorer.dismissed_title', 'Dismissed capture'),
            state: t('garden.explorer.state_dismissed', 'Dismissed, not counted as an animal')
        };
    }
    const title = view.name
        ?? (capture.status === 'pending'
            ? t('garden.explorer.possible_animal', 'Possible animal')
            : t('garden.explorer.unnamed_animal', 'Animal, not named'));
    if (capture.status === 'pending' && !view.review) return { title, state: t('garden.explorer.state_waiting_automatic', 'Waiting for automatic identification') };
    if (view.review === 'presence') {
        const reason = capture.automatic_check?.decision_reason;
        if (reason === 'location_required') return { title, state: t('garden.automatic_location_required', 'Animal detected. Set a country in Settings → Location so the model can name it automatically.') };
        if (reason === 'identity_unavailable') return { title, state: t('garden.automatic_identity_unavailable', 'Animal detected, but its name could not be bound to the local catalogue. No automatic name was saved.') };
        return { title, state: t('garden.explorer.state_manual', 'Manual review: automatic naming is off or an owner override is active') };
    }
    if (view.review === 'species') return { title, state: t('garden.explorer.state_species', 'Needs review: suggested species') };
    if (view.nameState === 'automatic') return { title, state: t('garden.explorer.state_automatic', 'Named automatically') };
    if (view.nameState === 'confirmed') {
        return { title, state: viewer === 'owner' ? t('garden.explorer.state_confirmed', 'Species confirmed by you') : t('visits.owner_confirmed', 'Owner confirmed') };
    }
    return { title, state: t('garden.explorer.state_unnamed', 'Animal confirmed, species not named') };
}

/** Which Garden captures the Garden view lists: animals (confirmed and waiting), or one review state. */
export type GardenReview = 'reviewable' | 'pending' | 'confirmed' | 'dismissed';

/** Whether a capture, after a review, still belongs to the Garden view it was opened from. */
export function gardenBelongs(capture: GardenCapture, review: GardenReview): boolean {
    return review === 'reviewable' ? capture.status === 'pending' || capture.status === 'confirmed' : capture.status === review;
}

/** The bird visit rule's gap: captures less than a minute apart are one stay. */
const GARDEN_VISIT_GAP_MS = 60_000;

export interface GardenVisit {
    id: string;
    captureCount?: number;
    /** The stay's first and last capture, when the server grouped it; a span reads as a bird visit's. */
    startTime?: string;
    endTime?: string;
    /** `position`: unconfirmed motion proposals around one spot. `visit`: one animal's stay, by time. */
    kind: 'position' | 'visit';
    /** In the order they were given, which is the page's display order. */
    items: GardenCapture[];
}

/**
 * The open group in a refreshed page of server visits.
 *
 * The server names a position stack after one of its photos, so reviewing that photo renames the
 * stack. A refreshed stack is still the open one when its representative is one of the open stack's
 * photos; without this, confirming the photo a stack is named after lost the stack. A visit whose
 * species changed is not followed here: that capture is re-read on its own.
 */
export function findRefreshedGardenVisit<T extends { id: string; kind: string; representative: { id: string } }>(
    visits: readonly T[],
    opened: Pick<GardenVisit, 'id' | 'kind' | 'items'> | null
): T | null {
    if (!opened) return null;
    const members = new Set(opened.items.map((item) => item.id));
    return visits.find((visit) => visit.id === opened.id)
        ?? (opened.kind === 'position'
            ? visits.find((visit) => visit.kind === 'position' && members.has(visit.representative.id))
            : undefined)
        ?? null;
}

/** What a capture is, for visit grouping: its name, or what is known before one is given. */
export function gardenVisitIdentity(capture: GardenCapture): string {
    const view = gardenEntryView(capture);
    const species = capture.owner_identification?.species_id ?? capture.identification?.species_id;
    if (view.name && species) return `species:${species}`;
    if (view.name) return `name:${view.name.trim().toLocaleLowerCase()}`;
    return capture.status === 'confirmed' ? 'animal' : `${capture.status}:${capture.frigate_label}`;
}

/**
 * Folds Garden captures into visits, as bird captures are: one camera, one animal, captures less
 * than a minute apart. Unconfirmed motion proposals keep their position stacks instead and never
 * merge by time, because a stationary false proposal at the feeder can run for hours and would
 * otherwise swallow a real animal passing through.
 */
export function groupGardenVisits(captures: readonly GardenCapture[]): GardenVisit[] {
    const order = new Map(captures.map((capture, index) => [capture.id, index]));
    const time = (capture: GardenCapture): number => Date.parse(capture.observed_at);
    const units = groupGardenReview(captures);
    const visits: GardenVisit[] = [];
    const open = new Map<string, { visit: GardenVisit; latest: number }>();
    const chronological = [...units].sort((a, b) => Math.min(...a.items.map(time)) - Math.min(...b.items.map(time)));
    for (const unit of chronological) {
        const first = unit.items[0];
        if (first.status === 'pending' && first.source_kind === 'motion') {
            visits.push({ id: `position:${unit.id}`, kind: unit.items.length > 1 ? 'position' : 'visit', items: unit.items });
            continue;
        }
        const key = `${first.camera}\u0000${gardenVisitIdentity(first)}`;
        const at = time(first);
        const current = open.get(key);
        if (current && at - current.latest <= GARDEN_VISIT_GAP_MS) {
            current.visit.items.push(first);
            current.latest = Math.max(current.latest, at);
        } else {
            const visit: GardenVisit = { id: `visit:${first.id}`, kind: 'visit', items: [first] };
            visits.push(visit);
            open.set(key, { visit, latest: at });
        }
    }
    const position = (capture: GardenCapture): number => order.get(capture.id) ?? 0;
    for (const visit of visits) visit.items.sort((a, b) => position(a) - position(b));
    return visits.sort((a, b) => position(a.items[0]) - position(b.items[0]));
}

/** How a grouped entry says what it holds, or null for a single capture. */
export function gardenVisitLabel(visit: GardenVisit | undefined, t: Translate): string | null {
    if (!visit || (visit.captureCount ?? visit.items.length) < 2) return null;
    const count = visit.captureCount ?? visit.items.length;
    return visit.kind === 'position'
        ? t('garden.explorer.group_photos', '{count, plural, one {# photo, same position} other {# photos, same position}}', { count })
        : t('garden.explorer.visit_captures', '{count, plural, one {# capture in this visit} other {# captures in this visit}}', { count });
}

/** What one capture inside an expanded Garden visit says beside its time, as a bird capture does. */
export interface GardenCaptureFacts {
    /** The capture the visit uses as its photograph, so the list can be read against the row. */
    shown: boolean;
    /** Proposed from retained motion footage rather than a Frigate event. */
    motion: boolean;
    /** What this capture still needs from a person, if anything. */
    review: GardenEntryView['review'];
}

export function gardenCaptureFacts(capture: GardenCapture, visit: GardenVisit): GardenCaptureFacts {
    return {
        shown: capture.id === visit.items[0]?.id,
        motion: capture.source_kind === 'motion',
        review: gardenEntryView(capture).review
    };
}
