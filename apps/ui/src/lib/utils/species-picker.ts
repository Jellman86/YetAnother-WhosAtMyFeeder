import type { SearchResult } from '../api';

export interface SpeciesPickerNames {
    primary: string;
    secondary: string | null;
}

/** How a species picker row reads: common name first, scientific name beneath when they differ. */
export function speciesPickerNames(result: SearchResult): SpeciesPickerNames {
    const common = result.common_name?.trim() || null;
    const scientific = result.scientific_name?.trim() || null;
    const fallback = result.display_name || result.id;
    if (common && scientific && common !== scientific) {
        return { primary: common, secondary: scientific };
    }
    return { primary: common || scientific || fallback, secondary: null };
}

interface NamedSpecies {
    display_name?: string | null;
    scientific_name?: string | null;
    common_name?: string | null;
}

/**
 * Leave out the species a record already carries: the picker is for choosing a
 * different one, and confirming the current one has its own button.
 */
export function withoutCurrentSpecies(results: SearchResult[], current: NamedSpecies | null | undefined): SearchResult[] {
    const names = new Set(
        [current?.display_name, current?.scientific_name, current?.common_name]
            .map((name) => name?.trim().toLowerCase())
            .filter((name): name is string => Boolean(name))
    );
    if (names.size === 0) return results;
    return results.filter(
        (result) =>
            ![result.id, result.display_name, result.scientific_name, result.common_name].some((name) =>
                names.has(String(name ?? '').trim().toLowerCase())
            )
    );
}
