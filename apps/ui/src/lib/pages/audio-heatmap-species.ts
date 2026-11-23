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

/** The filters a reading of the page was read under, and a key that tells two readings' filters apart. */
export interface AudioHeatmapReading {
    filters: AudioActivityHeatmapParams;
    key: string;
}

/** The reading the page applied, without paging (the grid has none) or filters left unset. */
export function audioHeatmapReading(
    pageParams: AudioActivityHeatmapParams & { limit?: number; offset?: number }
): AudioHeatmapReading {
    const filters: AudioActivityHeatmapParams = {};
    if (pageParams.days != null) filters.days = pageParams.days;
    if (pageParams.start_date != null) filters.start_date = pageParams.start_date;
    if (pageParams.end_date != null) filters.end_date = pageParams.end_date;
    if (pageParams.species) filters.species = pageParams.species;
    if (pageParams.source) filters.source = pageParams.source;
    if (pageParams.search) filters.search = pageParams.search;
    if (pageParams.only_hidden) filters.only_hidden = pageParams.only_hidden;
    if (pageParams.min_confidence != null) filters.min_confidence = pageParams.min_confidence;
    return { filters, key: JSON.stringify(filters) };
}

/**
 * One species' grid, read under every filter of the reading on screen, so it counts what the
 * figures beside it count, even while a newly chosen window is still being read or failed to read.
 */
export function audioSpeciesHeatmapParams(reading: AudioHeatmapReading, scientificName: string): AudioActivityHeatmapParams {
    return { ...reading.filters, scientific_name: scientificName };
}

/**
 * The species grid kept when the page reads again. A reading of the same filters (a refresh, a hidden
 * call, a guest's live update) keeps it, dimmed while it refreshes; one of other filters drops it.
 */
export function keptSpeciesHeatmap<T extends { readingKey: string }>(shown: T | null, reading: AudioHeatmapReading): T | null {
    return shown !== null && shown.readingKey === reading.key ? shown : null;
}
