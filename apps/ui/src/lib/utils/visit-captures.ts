import type { Detection } from '../api';
import type { DetectionVisit } from '../api/visits';

/** What one capture inside an expanded visit says beside its time. */
export interface CaptureFacts {
    /** The capture the visit uses as its photograph, so the list can be read against the row. */
    shown: boolean;
    /** Birds localized in this one capture, or null when that says no more than "a bird". */
    birds: number | null;
    /** A matching call was heard; a manual observation has no camera moment to match. */
    heard: boolean;
    /** The owner's favourite, so several in one visit can be told apart. */
    favorite: boolean;
}

/**
 * A single-capture visit is its own record, so listing its one capture beneath it only
 * repeats the row. The list exists once there is a sequence to read.
 */
export function hasCaptureTimeline(visit: DetectionVisit): boolean {
    return visit.capture_count > 1;
}

/**
 * Whether a standalone visit card has anything to say below itself: its list of captures, or the
 * birds counted in its busiest capture. Otherwise the card keeps its own plain, closed shape.
 */
export function hasCaptureFooter(visit: DetectionVisit): boolean {
    return hasCaptureTimeline(visit) || (visit.peak_capture?.bird_summary?.counted ?? 0) >= 2;
}

/**
 * Captures are never summed into a bird count: each states only its own stored count, and
 * a capture without one says nothing, because not counted is not zero.
 */
export function captureFacts(capture: Detection, visit: DetectionVisit): CaptureFacts {
    const counted = capture.bird_summary?.counted ?? 0;
    return {
        shown: capture.frigate_event === visit.representative.frigate_event,
        birds: counted >= 2 ? counted : null,
        heard: capture.observation_source !== 'manual_upload' && Boolean(capture.audio_confirmed),
        favorite: Boolean(capture.is_favorite)
    };
}

interface SpeciesInCapture {
    /** The stored label, usually the classifier's scientific name. */
    species: string;
    count: number;
    /** Catalogue names, when the label resolved, so the row names it as it names a visit. */
    common_name: string | null;
    scientific_name: string | null;
    /** Catalogue identity, when the label resolved: the surest way to tell two species apart. */
    species_id: number | null;
}

/** Other species seen in one capture of a visit, and the capture that shows them. */
export interface CompanionSpecies {
    /** The capture that holds them; the note about them opens it. */
    capture: Detection;
    /** That capture is the one the visit shows. */
    shown: boolean;
    /** Species other than the visit's own, most counted first. */
    species: SpeciesInCapture[];
}

function speciesKey(label: string | null | undefined): string {
    return (label ?? '').trim().toLocaleLowerCase();
}

/** One key per species: its catalogue id when it resolved, its label otherwise. */
function entryKey(entry: { species: string; species_id?: number | null }): string {
    return entry.species_id != null ? `id:${entry.species_id}` : `label:${speciesKey(entry.species)}`;
}

/**
 * Whether a counted species is the visit's own. Catalogue ids decide when both sides have one, so a
 * capture stored as "Blue Tit" still matches a box resolved to "Cyanistes caeruleus"; labels decide
 * only when an id is missing.
 */
function isVisitSpecies(entry: SpeciesInCapture, shown: Detection): boolean {
    if (entry.species_id != null && shown.species_id != null) return entry.species_id === shown.species_id;
    const labels = new Set(
        [shown.display_name, shown.category_name, shown.scientific_name, shown.common_name].map(speciesKey).filter(Boolean)
    );
    return [entry.species, entry.scientific_name, entry.common_name].some((label) => labels.has(speciesKey(label)));
}

/**
 * A visit is one species coming to the feeder, so it keeps that species' name. When its busiest
 * capture also holds other named species, they are a fact about that one capture, which may not be
 * the one the visit shows: the note names them and opens that capture. The rule matches the
 * "Multiple bird species" filter: two or more named species in one analyzed capture.
 * Owner-only evidence: a guest's visit carries no bird summary and has no note.
 */
export function visitCompanionSpecies(visit: DetectionVisit | undefined): CompanionSpecies | null {
    const capture = visit?.peak_capture;
    if (!visit || !capture) return null;
    const merged = new Map<string, SpeciesInCapture>();
    for (const entry of capture.bird_summary?.species ?? []) {
        if (!speciesKey(entry.species) || entry.count <= 0) continue;
        const key = entryKey(entry);
        const known = merged.get(key);
        if (known) known.count += entry.count;
        else merged.set(key, {
            species: entry.species,
            count: entry.count,
            common_name: entry.common_name ?? null,
            scientific_name: entry.scientific_name ?? null,
            species_id: entry.species_id ?? null
        });
    }
    if (merged.size < 2) return null;
    const shown = visit.representative;
    const others = [...merged.values()]
        .filter((entry) => !isVisitSpecies(entry, shown))
        .sort((a, b) => b.count - a.count || a.species.localeCompare(b.species));
    if (others.length === 0) return null;
    return { capture, shown: capture.frigate_event === shown.frigate_event, species: others };
}
