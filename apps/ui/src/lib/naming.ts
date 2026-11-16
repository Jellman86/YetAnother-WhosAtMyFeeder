import { get } from 'svelte/store';
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

/**
 * The one name the app prints for a visit without a species: sentence case and translated,
 * whatever casing the stored placeholder has.
 */
function unknownBirdName(): string {
    const fallback = 'Unknown bird';
    return get(locale) ? get(_)('common.unknown_bird', { default: fallback }) : fallback;
}

function named(value: string | null | undefined): string | null {
    if (!value) return null;
    return value.trim().toLowerCase() === UNRESOLVED_LABEL ? unknownBirdName() : value;
}

export function getBirdNames(
    item: BirdNamingInput,
    showCommon: boolean,
    preferSci: boolean
): NamingResult {
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
