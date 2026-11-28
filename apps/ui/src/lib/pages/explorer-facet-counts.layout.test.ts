import { describe, expect, it } from 'vitest';
import eventsPageSource from './Events.svelte?raw';
import filtersSource from '../components/ExplorerFilters.svelte?raw';
import searchSource from '../components/ExplorerSearch.svelte?raw';

describe('Explorer facet counts follow the filters (#1097)', () => {
    it('counts under the period, Visits or Captures and every other filter the rail holds', () => {
        const choice = eventsPageSource.slice(eventsPageSource.indexOf('const facetChoice = $derived<ExplorerFacetChoice>({'));
        const body = choice.slice(0, choice.indexOf('});'));
        for (const field of [
            'datePreset',
            'customStartDate',
            'customEndDate',
            'visits: groupVisits && !selectionMode',
            'species: speciesFilter',
            'taxon: taxonFilter',
            'camera: cameraFilter',
            'favoritesOnly',
            'audioConfirmedOnly',
            'multipleSpeciesOnly',
            'ownerConfirmedOnly',
            'onlyHidden: showHidden'
        ]) {
            expect(body).toContain(field);
        }
        expect(eventsPageSource).toContain('eventMetadataRefresh.load(forceRefresh, explorerFacetOptions(choice, window), () => read.generation === facetGeneration)');
    });

    it('reads the counts with the results, over the same window, and lets only the newest read settle them', () => {
        // One window per results read: the counts are asked for with its bounds, never a second clock.
        expect(eventsPageSource).toContain('const startFacetCounts = gardenOnly ? null : syncFacetCounts(facetChoice, range.request);');
        // The results are read first; the counts follow them.
        expect(eventsPageSource).toContain('startFacetCounts?.();');
        expect(eventsPageSource).toContain('if (read.generation !== facetGeneration) return;');
        expect(eventsPageSource).toContain("facetRead = { ...read, status: filters ? 'current' : 'failed' };");
        // No effect reads them on its own, with a clock of its own.
        expect(eventsPageSource).not.toContain('facetKeyRequested');
        expect(eventsPageSource).toContain('counts={facetCounts}');
    });

    it('reads whether Hidden is offered apart from the counts, so a replaced read cannot hide it', () => {
        expect(eventsPageSource).toContain('async function loadHiddenCount(): Promise<void> {');
        expect(eventsPageSource.match(/loadHiddenCount\(\)/g)?.length ?? 0).toBeGreaterThanOrEqual(4);
    });

    it('never shows a count read for other filters as the count of the filters chosen now', () => {
        expect(filtersSource).toContain("{#if count !== undefined && (counts === 'current' || counts === 'updating')}");
        expect(filtersSource).toContain("{:else if count !== undefined && counts === 'pending'}");
        expect(filtersSource).toMatch(/bg-line animate-pulse motion-reduce:animate-none" data-explorer-facet-count-pending/);
        // The lists that change are busy; the heading that says Counting stays readable.
        expect(filtersSource).toContain('aria-busy={busy} data-explorer-species-list');
        expect(filtersSource).not.toMatch(/aria-busy=\{counts === 'pending'\}\s*data-explorer-facets/);
        // A failure is announced from a region that is always there.
        expect(filtersSource).toMatch(/<p role="status"[^>]*data-explorer-facet-counts-unavailable>/);
    });

    it('names what the numbers count beside the species list, and reads each count with its unit', () => {
        expect(filtersSource).toContain('data-explorer-facet-unit>{countNote}');
        expect(filtersSource).toContain('<span class="sr-only">{spokenCount(count)}</span>');
        // A number and its placeholder take one width.
        expect(filtersSource.match(/min-w-12[^"]*" (aria-hidden="true" )?data-explorer-facet-slot/g)).toHaveLength(2);
        expect(filtersSource).toContain("events.filters.show_visits_short");
        expect(filtersSource).toContain("events.filters.show_captures_short");
    });

    it('counts hidden records under the filters, while offering the choice from all of history', () => {
        expect(filtersSource).toContain('{#if canSeeHidden && (hiddenCount > 0 || showHidden)}');
        expect(filtersSource).toContain('{@render chosenEnd(showHidden, totals?.hidden ?? 0)}');
    });

    it('labels search counts as visits or captures, and hides them while they are not current', () => {
        expect(eventsPageSource.match(/countsVisits=\{facetCountsVisits\}/g)).toHaveLength(2);
        expect(searchSource).toContain("{:else if option.kind === 'species' && counts === 'current'}");
        expect(searchSource).toContain("$_('visits.total'");
        expect(searchSource).toContain("option.count !== null && counts === 'current'");
        expect(searchSource).toContain('<span aria-hidden="true">{option.count}</span>');
    });
});
