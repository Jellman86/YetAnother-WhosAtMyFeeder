import { derived, type Readable } from 'svelte/store';
import { _, locale } from 'svelte-i18n';


export interface NamingResult {
    primary: string;
    secondary: string | null;
}

export interface BirdNamingInput {
    scientific_name?: string | null;
    common_name?: string | null;
    display_name?: string | null;
    species?: string | null;
}

/** The backend's placeholder label for a visit the classifier could not name. */
const UNRESOLVED_LABEL = 'unknown bird';

/** The one name for a visit without a species, in English: sentence case, whatever was stored. */
const UNKNOWN_BIRD = 'Unknown bird';

/**
 * Pure: the names of one bird under the reader's naming preference. `unknownName` is what a visit
 * without a species is called; a component takes it, translated, from `birdNames` below.
 */
export function getBirdNames(
    item: BirdNamingInput,
    showCommon: boolean,
    preferSci: boolean,
    unknownName: string = UNKNOWN_BIRD
): NamingResult {
    const named = (value: string | null | undefined): string | null => {
        if (!value) return null;
        return value.trim().toLowerCase() === UNRESOLVED_LABEL ? unknownName : value;
    };

    // Determine source values
    const scientificName = item.scientific_name || null;
    const commonName = named(item.common_name);

    // For Detection, we have display_name. For summary, we have species.
    const fallback = named(item.display_name) || named(item.species) || 'Unknown';

    let primary: string;
    let secondary: string | null = null;

    if (!showCommon) {
        // Strictly Scientific: Scientific primary, NO common name
        primary = scientificName || fallback;
        secondary = null;
    } else if (preferSci) {
        // Hobbyist: Scientific primary, Common sublabel
        primary = scientificName || fallback;
        secondary = commonName;
    } else {
        // Standard: Common primary, Scientific sublabel
        primary = commonName || fallback;
        secondary = scientificName;
    }

    // Ensure secondary is only returned if it's different from primary
    const finalSecondary = (secondary && secondary !== primary) ? secondary : null;

    return {
        primary,
        secondary: finalSecondary
    };
}

export type BirdNamer = (item: BirdNamingInput, showCommon: boolean, preferSci: boolean) => NamingResult;

/**
 * How a component names a bird: `$birdNames(detection, showCommon, preferSci)`. It is a store, so
 * a name derived from it is drawn again when the language changes and "Unknown bird" is never left
 * in the language the page was opened in.
 */
export const birdNames: Readable<BirdNamer> = derived([_, locale], ([$translate, $locale]) => {
    // The translator throws until a language is chosen; the English name stands in until then.
    const unknownName = $locale ? $translate('common.unknown_bird', { default: UNKNOWN_BIRD }) : UNKNOWN_BIRD;
    return (item: BirdNamingInput, showCommon: boolean, preferSci: boolean) => getBirdNames(item, showCommon, preferSci, unknownName);
});
