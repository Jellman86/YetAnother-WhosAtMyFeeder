import type { Detection } from '../api';
import type { DetectionVisit } from './visit-grouping';

type BirdSummary = NonNullable<Detection['bird_summary']>;

export interface VisitBirdMarker {
    /** The capture the marker describes, and the one it opens. */
    detection: Detection;
    summary: BirdSummary;
}

/**
 * What a visit row says about localized birds. Repeat frames of a visit can show the same birds
 * again, so captures are never summed: the row reports its single busiest capture. One bird is
 * what a visit row already implies, and a capture without stored evidence says nothing, because
 * "not counted" is not zero. Zero is stated only when every stored bird was excluded.
 */
export function visitBirdMarker(visit: DetectionVisit): VisitBirdMarker | null {
    let chosen: VisitBirdMarker | null = null;
    for (const detection of [visit.best, ...visit.frames.filter((frame) => frame !== visit.best)]) {
        const summary = detection.bird_summary;
        if (!summary) continue;
        if (!chosen || summary.counted > chosen.summary.counted) chosen = { detection, summary };
    }
    if (!chosen) return null;
    const { counted, excluded } = chosen.summary;
    return counted >= 2 || (counted === 0 && excluded > 0) ? chosen : null;
}
