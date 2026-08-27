import { describe, expect, it } from 'vitest';
import eventsSource from './Events.svelte?raw';
import filtersSource from '../components/ExplorerFilters.svelte?raw';
import paginationSource from '../components/Pagination.svelte?raw';

describe('Explorer page layout', () => {
    it('replaces the stacked selects with a token bar and counted facets', () => {
        expect(eventsSource).toContain('<ExplorerFilters');
        expect(filtersSource).toContain('data-events-filter-bar');
        expect(filtersSource).toContain('data-explorer-token');
        expect(filtersSource).toContain('data-explorer-facets');
        // Every option states how many results it would return before it is applied.
        expect(filtersSource).toContain('{item.count ?? 0}');
        expect(filtersSource).toContain('{cameraCounts[camera] ?? 0}');
        expect(filtersSource).toContain('{totals?.favorites ?? 0}');
        // The panel is closed until asked for, so the photographs are not pushed down.
        expect(filtersSource).toContain('let panelOpen = $state(false)');
    });

    it('passes naming-aware species labels to the responsive filter panel', () => {
        expect(eventsSource).toContain('let displaySpecies = $derived(');
        expect(eventsSource).toContain('display_name: formatSpeciesLabel(item)');
        expect(eventsSource).toContain('species={displaySpecies}');
        expect(eventsSource).not.toContain('species={availableSpecies}');
    });

    it('shows the complete species facet and lets it use the remaining desktop viewport', () => {
        expect(filtersSource).toContain("filterExplorerSpecies(species, search)");
        expect(filtersSource).not.toContain('.slice(0, 12)');
        expect(filtersSource).toContain('data-explorer-species-facet');
        expect(filtersSource).toContain('data-explorer-species-list');
        expect(filtersSource).toContain('lg:max-h-[calc(100dvh-2rem)]');
        expect(filtersSource).toContain('lg:min-h-0 lg:max-h-none lg:flex-1');
    });

    it('separates the timeline and pagination with space, not rules', () => {
        expect(eventsSource).toContain('data-events-timeline');
        // Both used to be wrapped in a rule above and below. Against a grid of cards that
        // already carry strong edges, those read as lines drawn across the page.
        expect(eventsSource).not.toMatch(/data-events-timeline[^>]+border-y/);
        expect(paginationSource).toContain('data-pagination');
        expect(paginationSource).not.toMatch(/data-pagination[^>]+border-y/);
        expect(paginationSource).not.toContain('card-base');
        expect(paginationSource).toContain("$_('pagination.showing'");
        expect(paginationSource).not.toContain('Showing <span');
        expect(paginationSource).toContain('sm:hidden');
        expect(paginationSource).toContain('hidden items-center gap-1 sm:flex');
    });

    it('labels the page-level selection toggle as Multi Select', () => {
        expect(eventsSource).toContain('{#if authStore.hasOwnerAccess}');
        expect(eventsSource).toContain("$_('common.multi_select', { default: 'Multi Select' })");
        expect(eventsSource).not.toContain("selectionMode ? $_('common.cancel') : $_('common.select', { default: 'Select' })");
    });

    it('keeps selection wording in the bulk toolbar instead of inside each card', () => {
        expect(eventsSource).toContain('{#if authStore.hasOwnerAccess && selectionMode}');
        expect(eventsSource).toContain('{#if authStore.hasOwnerAccess && showBulkTagModal}');
        expect(eventsSource).toContain("selectedEventIds.length");
        expect(eventsSource).toContain("$_('common.selected', { default: 'selected' })");
        expect(eventsSource).toContain("$_('common.select', { default: 'Select' }) + ' events to act on.'");
    });

    it('treats AI analysis fields as part of selected-event sync state', () => {
        expect(eventsSource).toContain('asText(d.ai_analysis)');
        expect(eventsSource).toContain('asText(d.ai_analysis_timestamp)');
    });

    it('refreshes filter metadata after delete and hide mutations', () => {
        expect(eventsSource).toContain('await refreshEventMetadata(true, false);');
    });

    it('wires modal delete and hide success back into page refresh logic', () => {
        expect(eventsSource).toContain('onDeleteSuccess={async (deletedEventId: string, detectionTime?: string) => {');
        expect(eventsSource).toContain('onHideSuccess={async (hiddenEventId: string, detectionTime: string | undefined, isHidden: boolean) => {');
    });

    it('exposes hidden detections through an owner-only facet', () => {
        expect(eventsSource).toContain('canSeeHidden={authStore.hasOwnerAccess}');
        expect(filtersSource).toContain('{#if canSeeHidden && (hiddenCount > 0 || showHidden)}');
        expect(filtersSource).toContain("$_('events.filters.hidden', { default: 'Hidden' })");
        expect(filtersSource).toContain('data-explorer-hidden-facet');
    });

    it('keeps the capabilities the old filter bar carried', () => {
        // Custom range, refresh options and hidden all survived the rebuild.
        expect(filtersSource).toContain("datePreset === 'custom'");
        expect(filtersSource).toContain('events.filters.refresh_options');
        expect(eventsSource).toContain('onrefresh={() => refreshEventMetadata(true, true)}');
        expect(filtersSource).toContain('events.filters.start_date');
        expect(filtersSource).toContain('events.filters.end_date');
    });
});
