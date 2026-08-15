import { KM_PER_MILE, type WeatherUnitSystem } from './weather-units';

// eBird's own API limits, not a YA-WAMF preference: `dist` is rejected outside
// this range, so the stored radius stays in kilometres whatever the owner sees.
export const EBIRD_RADIUS_MIN_KM = 1;
export const EBIRD_RADIUS_MAX_KM = 50;

export interface EbirdRadiusBounds {
    min: number;
    max: number;
}

function showsMiles(system: WeatherUnitSystem): boolean {
    return system !== 'metric';
}

function clampToStoredRange(valueKm: number): number {
    return Math.min(EBIRD_RADIUS_MAX_KM, Math.max(EBIRD_RADIUS_MIN_KM, valueKm));
}

/** The range the owner may type, expressed in whatever unit they are shown. */
export function getEbirdRadiusBounds(system: WeatherUnitSystem): EbirdRadiusBounds {
    if (!showsMiles(system)) {
        return { min: EBIRD_RADIUS_MIN_KM, max: EBIRD_RADIUS_MAX_KM };
    }
    return {
        min: Math.max(1, Math.ceil(EBIRD_RADIUS_MIN_KM / KM_PER_MILE)),
        max: Math.floor(EBIRD_RADIUS_MAX_KM / KM_PER_MILE)
    };
}

/** Stored kilometres to the number shown in the settings field. */
export function ebirdRadiusToDisplayValue(radiusKm: number, system: WeatherUnitSystem): number {
    return showsMiles(system) ? Math.round(radiusKm / KM_PER_MILE) : Math.round(radiusKm);
}

/**
 * An edited field back to stored kilometres, or `null` while the field is empty
 * or unparseable so the caller can leave the saved radius alone.
 */
export function ebirdRadiusFromDisplayValue(
    value: number | null | undefined,
    system: WeatherUnitSystem
): number | null {
    if (value === null || value === undefined || Number.isNaN(value)) {
        return null;
    }
    const km = showsMiles(system) ? value * KM_PER_MILE : value;
    return clampToStoredRange(Math.round(km));
}
