import { describe, expect, it } from 'vitest';
import eventsPageSource from './Events.svelte?raw';
import filtersSource from '../components/ExplorerFilters.svelte?raw';
import rowSource from '../components/DetectionRow.svelte?raw';
import storeSource from '../stores/explorer_filters.svelte.ts?raw';

describe('collapsing the Explorer filter rail', () => {
    it('gives the rail width back to the detections when it is collapsed', () => {
        // The 14rem column is only worth holding while the rail is showing.
        expect(eventsPageSource).toContain("explorerFiltersStore.collapsed");
        expect(eventsPageSource).toContain("'lg:grid-cols-[14rem_minmax(0,1fr)]'");
    });

    it('offers the control on desktop only, since a phone already has one', () => {
        expect(filtersSource).toContain('data-explorer-rail-toggle');
        expect(filtersSource).toContain('hidden min-h-11 px-3 py-2 text-xs lg:inline-flex');
        // The existing Filters button is what a phone uses, and what a collapsed
        // desktop uses too, so it stops hiding itself at lg when collapsed.
        expect(filtersSource).toContain("{collapsed ? '' : 'lg:hidden'}");
    });

    it('says which state it is in, not just which way the chevron points', () => {
        expect(filtersSource).toContain('aria-expanded={!collapsed}');
        expect(filtersSource).toContain('aria-controls="explorer-facets"');
        expect(filtersSource).toContain("events.filters.show_rail");
        expect(filtersSource).toContain("events.filters.hide_rail");
    });

    it('remembers the choice on the device that made it', () => {
        expect(storeSource).toContain("'yawamf:explorer-filters-collapsed'");
        expect(storeSource).toContain('try {');
    });
});

describe('the Explorer list row preview', () => {
    it('uses the shared pop-out rather than a second static thumbnail', () => {
        // DetectionPreview carries the hover contract: focus as well as hover, a
        // close grace window, Escape, and no second image request.
        expect(rowSource).toContain('<DetectionPreview');
        expect(rowSource).toContain("import DetectionPreview from './DetectionPreview.svelte'");
    });

    it('no longer loads its own image', () => {
        expect(rowSource).not.toContain('getThumbnailUrl');
        expect(rowSource).not.toContain('imageLoaded');
    });

    it('opens the same detection the row opens', () => {
        expect(rowSource).toContain('onopen={() => onclick?.()}');
    });
});
