import type { AudioActivityHeatmapParams } from '../api';
import { HEATMAP_SPECIES_CHOICES } from '../leaderboard/heatmap';
import { distinctSeriesLabels } from '../utils/distinct-series-labels';

export interface AudioHeatmapSpeciesOption {
    /** The scientific name the grid is asked for. */
    key: string;
    label: string;
    count: number;
}

interface HeardSpecies {
    species: string;
    scientific_name?: string | null;
    count: number;
}

/**
 * The species the calls grid offers to show on their own: the most heard in the window, by calls.
 *
 * A species is asked for by its scientific name, because the name shown is translated and the page's
 * species search is a substring match that would also count every name containing it. Rows stored
 * without a scientific name cannot be asked for exactly, so they are not offered. While the page is
 * filtered to a species the grid already shows only that search, and a second species control
 * beside it could only repeat or contradict it, so none is offered.
 */
export function audioHeatmapSpeciesOptions(
    topSpecies: readonly HeardSpecies[],
    pageSpeciesFilter: string
): AudioHeatmapSpeciesOption[] {
    if (pageSpeciesFilter.trim()) return [];
    const bySpecies = new Map<string, { key: string; name: string; count: number }>();
    for (const row of topSpecies) {
        const key = row.scientific_name?.trim();
        if (!key || row.count <= 0) continue;
        const folded = key.toLowerCase();
        const known = bySpecies.get(folded);
        if (known) known.count += row.count;
        else bySpecies.set(folded, { key, name: row.species, count: row.count });
    }
    const chosen = [...bySpecies.values()].sort((a, b) => b.count - a.count).slice(0, HEATMAP_SPECIES_CHOICES);
    const labels = distinctSeriesLabels(chosen.map((row) => ({ name: row.name, qualifier: row.key })));
    return chosen.map((row, index) => ({ key: row.key, label: labels[index], count: row.count }));
}

/** One species' grid, read under every filter the page applies so it counts what the page counts. */
export function audioSpeciesHeatmapParams(
    pageParams: AudioActivityHeatmapParams & { limit?: number; offset?: number },
    scientificName: string
): AudioActivityHeatmapParams {
    const { limit: _limit, offset: _offset, ...filters } = pageParams;
    return { ...filters, scientific_name: scientificName };
}
