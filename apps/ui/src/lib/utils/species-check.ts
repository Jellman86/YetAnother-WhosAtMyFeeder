import type { SearchResult, SnapshotCandidate } from '../api';

/**
 * The decisions behind the leaderboard's check sheet, kept pure so the sheet only draws them.
 *
 * A flagged species is one the camera alone backs and no birder has reported nearby. The sheet
 * shows what the camera actually photographed and offers the likeliest answer first. Every answer
 * it offers is grounded in something stored: another reading of the same crops, the feeder's own
 * history, or the catalogue saying the species is not a bird at all.
 */

const PHOTO_ONLY = new Set(['full_frame', 'retained_photo']);

const key = (value: string | null | undefined): string => (value ?? '').trim().toLocaleLowerCase();

/** The visit's best crop: a cut around the bird, never the whole scene, ranked as the record ranks it. */
export function bestCrop(candidates: SnapshotCandidate[]): SnapshotCandidate | null {
    const crops = candidates.filter(
        (candidate) => !PHOTO_ONLY.has(candidate.source_mode) && !candidate.photo_hidden && Boolean(candidate.thumbnail_url || candidate.image_url)
    );
    return crops.find((candidate) => candidate.selected) ?? [...crops].sort((a, b) => b.ranking_score - a.ranking_score)[0] ?? null;
}

/** Species the visit's own crops were also read as, besides the name it carries. */
export function otherReads(candidates: SnapshotCandidate[], current: string | null | undefined): string[] {
    const currentKey = key(current);
    const reads = new Set<string>();
    for (const candidate of candidates) {
        if (PHOTO_ONLY.has(candidate.source_mode)) continue;
        const label = key(candidate.classifier_label);
        if (label && label !== currentKey) reads.add(label);
    }
    return [...reads];
}

export type CheckSuggestion =
    | { kind: 'rename'; target: SearchResult; reason: 'other_reads'; visits: number }
    | { kind: 'rename'; target: SearchResult; reason: 'most_common' }
    | { kind: 'confirm'; reason: 'not_a_bird_confident' }
    | { kind: 'hide'; reason: 'not_a_bird_unsure' };

export interface SuggestionInput {
    /** For each visit, the scientific names its crops were also read as. */
    readsPerVisit: string[][];
    /** This feeder's species, most visits first, without the flagged species itself. */
    feeder: SearchResult[];
    /** The catalogue's word on whether it is a bird; null when it could not be asked. */
    isBird: boolean | null;
    /** The best score among the flagged visits. */
    bestScore: number;
}

/** A confident camera on something birders never report, a mammal, is most likely right. */
const CONFIDENT = 0.9;

export function suggestAnswer(input: SuggestionInput): CheckSuggestion | null {
    if (input.isBird === false) {
        return input.bestScore >= CONFIDENT ? { kind: 'confirm', reason: 'not_a_bird_confident' } : { kind: 'hide', reason: 'not_a_bird_unsure' };
    }
    const visitsByRead = new Map<string, number>();
    for (const reads of input.readsPerVisit) {
        for (const read of new Set(reads)) visitsByRead.set(read, (visitsByRead.get(read) ?? 0) + 1);
    }
    // Only a read this feeder has seen before is offered: a stray label from the wider model
    // (a lizard, a plant) is not a better answer than the one it replaces.
    const reread = input.feeder
        .map((species) => ({ species, visits: visitsByRead.get(key(species.scientific_name)) ?? 0 }))
        .filter((entry) => entry.visits > 0)
        .sort((a, b) => b.visits - a.visits)[0];
    if (reread) return { kind: 'rename', target: reread.species, reason: 'other_reads', visits: reread.visits };
    const common = input.feeder[0];
    return common ? { kind: 'rename', target: common, reason: 'most_common' } : null;
}

/** The catalogue holds birds; a species it places outside class Aves, or cannot place, is not one. */
export function isBirdLineage(lineage: { rank: string; scientific_name: string }[] | null): boolean | null {
    if (lineage === null) return null;
    return lineage.some((taxon) => taxon.rank === 'class' && key(taxon.scientific_name) === 'aves');
}

/** The other quick answers: the feeder's regulars, without the suggestion already shown above them. */
export function regulars(feeder: SearchResult[], suggestion: CheckSuggestion | null, limit = 4): SearchResult[] {
    const shown = suggestion?.kind === 'rename' ? suggestion.target.id : null;
    return feeder.filter((species) => species.id !== shown).slice(0, limit);
}
