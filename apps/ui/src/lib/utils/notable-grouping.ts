/**
 * Fold repeated reports of one species into a single card.
 *
 * eBird returns one observation per checklist, so a rarity seen by four people
 * at the same reserve on the same morning arrives as four identical rows. One
 * card per species says the same thing with room to say how many saw it and
 * where, which is the part a person actually wants to know.
 */
export interface NotableObservationLike {
    species_code?: string | null;
    common_name?: string | null;
    scientific_name?: string | null;
    observed_at?: string | null;
    location_name?: string | null;
    how_many?: number | null;
    thumbnail_url?: string | null;
}

export interface NotableSpeciesGroup<T extends NotableObservationLike> {
    key: string;
    /** The most recent report; its names and thumbnail front the card. */
    latest: T;
    reports: number;
    locations: string[];
    thumbnail_url: string | null;
}

function keyFor(observation: NotableObservationLike): string {
    const scientific = (observation.scientific_name ?? '').trim().toLowerCase();
    if (scientific) return `sci:${scientific}`;
    const common = (observation.common_name ?? '').trim().toLowerCase();
    if (common) return `name:${common}`;
    return `code:${(observation.species_code ?? '').trim().toLowerCase()}`;
}

function isLater(candidate: string | null | undefined, current: string | null | undefined): boolean {
    if (!candidate) return false;
    if (!current) return true;
    return candidate > current;
}

export function groupNotableObservations<T extends NotableObservationLike>(observations: T[]): NotableSpeciesGroup<T>[] {
    const groups = new Map<string, NotableSpeciesGroup<T>>();
    for (const observation of observations) {
        const key = keyFor(observation);
        const location = (observation.location_name ?? '').trim();
        const existing = groups.get(key);
        if (!existing) {
            groups.set(key, {
                key,
                latest: observation,
                reports: 1,
                locations: location ? [location] : [],
                thumbnail_url: observation.thumbnail_url ?? null
            });
            continue;
        }
        existing.reports += 1;
        if (location && !existing.locations.includes(location)) existing.locations.push(location);
        if (!existing.thumbnail_url && observation.thumbnail_url) existing.thumbnail_url = observation.thumbnail_url;
        if (isLater(observation.observed_at, existing.latest.observed_at)) existing.latest = observation;
    }
    // First appearance order: eBird already lists the newest first.
    return [...groups.values()];
}
