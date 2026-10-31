import type { ExplorerSubjects, GardenReview } from './garden-explorer';

/**
 * The Explorer's filters as an address, so reloading, going back or sharing a link opens the
 * same view.
 *
 * The address is untrusted: anything a link names that is not a value the rail could choose is
 * ignored, never sent on. Owner-only filters are read and written for the owner alone. Keys the
 * Explorer does not own (a shared clip's `event`, `share` and `video`) are left as they are.
 */

export type ExplorerDatePreset = 'all' | 'today' | 'week' | 'month' | 'custom';

export interface ExplorerQuery {
    /** Null when the link does not say, so this device's own choice applies. */
    subjects: ExplorerSubjects | null;
    gardenReview: GardenReview;
    datePreset: ExplorerDatePreset;
    customStartDate: string;
    customEndDate: string;
    speciesFilter: string;
    cameraFilter: string;
    favoritesOnly: boolean;
    audioConfirmedOnly: boolean;
    multipleSpeciesOnly: boolean;
    showHidden: boolean;
    /** Visits (one bird's stay) or every capture on its own. */
    groupVisits: boolean;
    page: number;
}

export interface ExplorerQueryAccess {
    owner: boolean;
    /** Whether Garden animals are readable here; until that is known, Garden keys are left alone. */
    gardenAvailable: boolean;
}

const OWNED_KEYS = ['visitors', 'review', 'date', 'start', 'end', 'species', 'camera', 'favorites', 'audio', 'multiple', 'hidden', 'show', 'page'] as const;
const GARDEN_KEYS = new Set<string>(['visitors', 'review']);
const SUBJECTS: readonly ExplorerSubjects[] = ['birds', 'garden', 'all'];
const REVIEWS: readonly GardenReview[] = ['pending', 'confirmed', 'dismissed'];
const DATE_PRESETS: readonly ExplorerDatePreset[] = ['all', 'today', 'week', 'month', 'custom'];
// The API refuses longer camera names, and no species value comes near this.
const MAX_NAME_LENGTH = 128;
const MAX_SPECIES_LENGTH = 256;
const MAX_PAGE = 100_000;

export function defaultExplorerQuery(): ExplorerQuery {
    return {
        subjects: null,
        gardenReview: 'reviewable',
        datePreset: 'all',
        customStartDate: '',
        customEndDate: '',
        speciesFilter: '',
        cameraFilter: '',
        favoritesOnly: false,
        audioConfirmedOnly: false,
        multipleSpeciesOnly: false,
        showHidden: false,
        groupVisits: true,
        page: 1
    };
}

function oneOf<T extends string>(value: string | null, allowed: readonly T[]): T | null {
    return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : null;
}

function flag(value: string | null): boolean {
    return value === '1' || value === 'true';
}

/** A name as the rail would hold it: printable, trimmed and of a length the API accepts. */
function name(value: string | null, maxLength: number): string {
    const trimmed = value?.trim() ?? '';
    if (!trimmed || trimmed.length > maxLength || /[\u0000-\u001f\u007f]/.test(trimmed)) return '';
    return trimmed;
}

/** A real calendar day written YYYY-MM-DD, as a date input gives it. */
function calendarDay(value: string | null): string {
    if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return '';
    const [year, month, day] = value.split('-').map(Number);
    const date = new Date(Date.UTC(year, month - 1, day));
    return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day ? value : '';
}

function pageNumber(value: string | null): number {
    if (!value || !/^\d+$/.test(value)) return 1;
    const page = Number(value);
    return page >= 1 && page <= MAX_PAGE ? page : 1;
}

export function parseExplorerQuery(search: string | URLSearchParams, access: Pick<ExplorerQueryAccess, 'owner'>): ExplorerQuery {
    const params = typeof search === 'string' ? new URLSearchParams(search) : search;
    const query = defaultExplorerQuery();
    query.subjects = oneOf(params.get('visitors'), SUBJECTS);
    // Visitors see confirmed animals only, so a shared review link cannot label their view.
    if (access.owner) query.gardenReview = oneOf(params.get('review'), REVIEWS) ?? 'reviewable';

    let start = calendarDay(params.get('start'));
    let end = calendarDay(params.get('end'));
    // A window that ends before it starts cannot be what was meant.
    if (start && end && start > end) {
        start = '';
        end = '';
    }
    const preset = oneOf(params.get('date'), DATE_PRESETS);
    query.datePreset = preset ?? (start || end ? 'custom' : 'all');
    if (query.datePreset === 'custom') {
        query.customStartDate = start;
        query.customEndDate = end;
    }

    query.speciesFilter = name(params.get('species'), MAX_SPECIES_LENGTH);
    query.cameraFilter = name(params.get('camera'), MAX_NAME_LENGTH);
    query.favoritesOnly = flag(params.get('favorites'));
    query.audioConfirmedOnly = flag(params.get('audio'));
    if (access.owner) {
        query.multipleSpeciesOnly = flag(params.get('multiple'));
        query.showHidden = flag(params.get('hidden'));
    }
    query.groupVisits = params.get('show') !== 'captures';
    query.page = pageNumber(params.get('page'));
    return query;
}

/**
 * The address search for this view: the keys other features own kept, the Explorer's replaced.
 * Returns the search without its leading `?`, empty when nothing is chosen.
 */
export function writeExplorerQuery(current: string | URLSearchParams, query: ExplorerQuery, access: ExplorerQueryAccess): string {
    const params = new URLSearchParams(current);
    for (const key of OWNED_KEYS) {
        if (GARDEN_KEYS.has(key) && !access.gardenAvailable) continue;
        params.delete(key);
    }
    if (access.gardenAvailable && query.subjects) {
        params.set('visitors', query.subjects);
        if (access.owner && query.subjects === 'garden' && query.gardenReview !== 'reviewable') params.set('review', query.gardenReview);
    }
    if (query.datePreset !== 'all') params.set('date', query.datePreset);
    if (query.datePreset === 'custom') {
        if (query.customStartDate) params.set('start', query.customStartDate);
        if (query.customEndDate) params.set('end', query.customEndDate);
    }
    if (query.speciesFilter) params.set('species', query.speciesFilter);
    if (query.cameraFilter) params.set('camera', query.cameraFilter);
    if (query.favoritesOnly) params.set('favorites', '1');
    if (query.audioConfirmedOnly) params.set('audio', '1');
    if (access.owner && query.multipleSpeciesOnly) params.set('multiple', '1');
    if (access.owner && query.showHidden) params.set('hidden', '1');
    if (!query.groupVisits) params.set('show', 'captures');
    if (query.page > 1) params.set('page', String(query.page));
    return params.toString();
}
