/**
 * What stands behind a species' place on the leaderboard, beyond the classifier's word.
 *
 * A model that knows eleven thousand labels will name a Dunnock "Golden-crowned Sparrow" now and
 * then, and the leaderboard used to print both with the same confidence. A person naming a
 * detection, or BirdNET hearing the species in the same window, is independent evidence; a row
 * with neither is the camera's claim alone, and the page says so rather than implying more.
 */
export type SpeciesEvidence =
    | 'confirmed'
    | 'seen_and_heard'
    | 'heard_only'
    | 'camera_only'
    | 'unconfirmed'
    | 'unknown';

export interface EvidenceRow {
    count: number;
    heard_count: number;
    /** Detections a person named or confirmed in the window; null when the route did not say. */
    confirmed_count?: number | null;
    audio_only?: boolean;
}

export interface EvidenceContext {
    /** BirdNET is on and its window loaded, so a zero heard count means "not heard". */
    audioKnown: boolean;
}

export function evidenceFor(row: EvidenceRow, context: EvidenceContext): SpeciesEvidence {
    if (row.audio_only) return 'heard_only';
    if ((row.confirmed_count ?? 0) > 0) return 'confirmed';
    if (context.audioKnown && row.heard_count > 0) return 'seen_and_heard';
    if (row.confirmed_count === null || row.confirmed_count === undefined) return 'unknown';
    return context.audioKnown ? 'camera_only' : 'unconfirmed';
}

/** Species whose place rests on more than the camera: confirmed, heard as well, or heard only. */
export function isCorroborated(evidence: SpeciesEvidence): boolean {
    return evidence === 'confirmed' || evidence === 'seen_and_heard' || evidence === 'heard_only';
}
