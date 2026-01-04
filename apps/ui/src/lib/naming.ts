
import type { Detection, DailySpeciesSummary } from './api';

export interface NamingResult {
    primary: string;
    secondary: string | null;
}

export function getBirdNames(
    item: Detection | DailySpeciesSummary,
    showCommon: boolean,
    preferSci: boolean
): NamingResult {
    // Determine source values
    const scientificName = item.scientific_name || null;
    const commonName = item.common_name || null;
    
    // For Detection, we have display_name. For summary, we have species.
    const fallback = (item as Detection).display_name || (item as DailySpeciesSummary).species || 'Unknown';

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
