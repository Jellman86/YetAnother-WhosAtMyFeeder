import { describe, expect, it } from 'vitest';
import eventsPageSource from './Events.svelte?raw';
import filtersSource from '../components/ExplorerFilters.svelte?raw';
import rowSource from '../components/DetectionRow.svelte?raw';
import storeSource from '../stores/explorer_filters.svelte.ts?raw';
import previewSource from '../components/DetectionPreview.svelte?raw';

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

    it('does not fold the rail away while leaving the facets on screen', () => {
        // The collapsed desktop shares the phone's Filters button, so collapsing
        // with that panel open would contradict the control's own label.
        expect(filtersSource).toContain('panelOpen = false;\n                oncollapsechange?.(!collapsed);');
    });

    it('keeps the control in one place instead of walking across the screen', () => {
        // The view toggle is pushed right by `ml-auto`. In the rail that right
        // edge is 14rem away; collapsed it is the far side of the window, so a
        // control placed after the toggle travelled the width of the screen as
        // you used it. It sits beside the result count, which does not move.
        const countAt = filtersSource.indexOf('events.filters.result_count');
        const railToggleAt = filtersSource.indexOf('data-explorer-rail-toggle');
        const autoMarginAt = filtersSource.indexOf('class="ml-auto');
        expect(countAt).toBeGreaterThan(-1);
        expect(railToggleAt).toBeGreaterThan(countAt);
        expect(railToggleAt).toBeLessThan(autoMarginAt);
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

    it('escapes the list frame instead of being clipped by it', () => {
        // The Explorer's list rounds its corners with `overflow-hidden`, which
        // clipped a panel positioned inside a row, and a later row's controls
        // could paint over what survived. Neither is fixable from inside the
        // row, so the panel is portalled to the body and placed in viewport
        // coordinates.
        expect(previewSource).toContain('use:portal');
        expect(previewSource).toContain('getBoundingClientRect()');
        expect(previewSource).toMatch(/class="fixed z-\[70\]/);
        expect(eventsPageSource).toContain('overflow-hidden rounded-2xl');
    });

    it('closes rather than pointing at the wrong row once the page moves', () => {
        expect(previewSource).toContain("window.addEventListener('scroll', close, true)");
        expect(previewSource).toContain("window.addEventListener('resize', close)");
    });

    it('flips above the thumbnail when there is no room below', () => {
        expect(previewSource).toContain('above: boolean');
        expect(previewSource).toContain('-translate-y-full');
    });
});
