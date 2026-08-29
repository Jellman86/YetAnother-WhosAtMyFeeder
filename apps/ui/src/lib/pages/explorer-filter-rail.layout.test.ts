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

    it('sits in the header toolbar beside the view switch and Multi-select', () => {
        // Inside the rail, the toolbar controls wrapped vertically down a 14rem
        // column while Multi-select sat alone in the header: three ways of
        // acting on the same list in two places and two styles. One row now.
        const railToggleAt = eventsPageSource.indexOf('data-explorer-rail-toggle');
        const viewToggleAt = eventsPageSource.indexOf('data-explorer-view-toggle');
        const multiSelectAt = eventsPageSource.indexOf('common.multi_select');
        expect(railToggleAt).toBeGreaterThan(-1);
        expect(viewToggleAt).toBeGreaterThan(railToggleAt);
        expect(multiSelectAt).toBeGreaterThan(viewToggleAt);
        expect(filtersSource).not.toContain('data-explorer-rail-toggle');
        expect(filtersSource).not.toContain('data-explorer-view-toggle');
    });

    it('offers the rail control on desktop only, since a phone already has one', () => {
        expect(eventsPageSource).toContain('btn btn-secondary hidden min-h-11 px-3 py-2 text-xs lg:inline-flex');
        // The existing Filters button is what a phone uses, and what a collapsed
        // desktop uses too, so it stops hiding itself at lg when collapsed.
        expect(filtersSource).toContain("{collapsed ? '' : 'lg:hidden'}");
    });

    it('says which state it is in, and which region it actually controls', () => {
        expect(eventsPageSource).toContain('aria-expanded={!explorerFiltersStore.collapsed}');
        expect(eventsPageSource).toContain('aria-controls="explorer-filter-rail"');
        expect(eventsPageSource).toContain('id="explorer-filter-rail"');
        expect(eventsPageSource).toContain('events.filters.show_rail');
        expect(eventsPageSource).toContain('events.filters.hide_rail');
        // The facets panel belongs to the Filters button alone, so the two
        // controls no longer publish contradictory expanded states for one
        // region when the rail is collapsed and the panel is open.
        expect(filtersSource).not.toContain('aria-controls="explorer-facets"\n            aria-expanded={!collapsed}');
        expect(filtersSource).toMatch(/aria-controls="explorer-facets"[\s\S]{0,200}data-explorer-filter-toggle/);
    });

    it('does not fold the rail away while leaving the facets on screen', () => {
        // Collapsing arrives from the header now, so the rail closes its own
        // panel when the collapse lands - while keeping collapsed-with-panel-
        // open valid, since that is exactly what the Filters button opens.
        expect(filtersSource).toContain('previousCollapsed');
        expect(filtersSource).toContain('panelOpen = false');
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

    it('follows its row when the page moves, closing only when the row leaves', () => {
        // Closing on the first scroll broke the keyboard path: focusing a
        // trigger below the fold scrolls it into view, and that scroll landed
        // right after the panel opened, dismissing it in the same frame.
        expect(previewSource).toContain('requestAnimationFrame');
        expect(previewSource).toContain("window.addEventListener('scroll', follow, true)");
        expect(previewSource).toContain("window.addEventListener('resize', follow)");
        expect(previewSource).not.toContain("window.addEventListener('scroll', close");
    });

    it('stands aside in selection mode instead of hijacking it', () => {
        // Activating a control announced as "Preview" must not toggle the
        // row's selection; in selection mode the row overlay, labelled for
        // selecting, owns every activation and the thumbnail is decoration.
        expect(rowSource).toContain('interactive={!selectionMode}');
        expect(previewSource).toContain('{#if interactive}');
    });

    it('flips above the thumbnail when there is no room below', () => {
        expect(previewSource).toContain('above: boolean');
        expect(previewSource).toContain('-translate-y-full');
    });
});
