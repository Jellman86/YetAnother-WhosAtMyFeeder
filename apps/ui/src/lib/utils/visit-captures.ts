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

export interface SpeciesInCapture {
    species: string;
    count: number;
}

/**
 * The species in a visit's busiest capture, when there is more than one. That capture is a single
 * moment, so its species and counts are a statement about one frame, never a sum across repeats.
 * Owner-only evidence: a guest's visit carries no bird summary and stays a one-species row.
 */
export function visitSpeciesMix(visit: DetectionVisit | undefined): SpeciesInCapture[] | null {
    const species = visit?.peak_capture?.bird_summary?.species ?? [];
    const merged = new Map<string, SpeciesInCapture>();
    for (const entry of species) {
        const key = entry.species.trim().toLocaleLowerCase();
        if (!key || entry.count <= 0) continue;
        const known = merged.get(key);
        if (known) known.count += entry.count;
        else merged.set(key, { species: entry.species, count: entry.count });
    }
    if (merged.size < 2) return null;
    return [...merged.values()].sort((a, b) => b.count - a.count || a.species.localeCompare(b.species));
}
