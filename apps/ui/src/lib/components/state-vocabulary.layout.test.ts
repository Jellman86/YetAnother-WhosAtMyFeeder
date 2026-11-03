// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import searchSource from './ExplorerSearch.svelte?raw';
import filtersSource from './ExplorerFilters.svelte?raw';
import detectionRowSource from './DetectionRow.svelte?raw';
import gardenExplorerRowSource from './GardenExplorerRow.svelte?raw';
import fieldLogVisitRowSource from './FieldLogVisitRow.svelte?raw';
import fieldLogGardenRowSource from './FieldLogGardenRow.svelte?raw';
import eventsSource from '../pages/Events.svelte?raw';

const appCss = readFileSync(new URL('../../app.css', import.meta.url), 'utf8');

/**
 * Owner, 2026-11-03: "The new elements that have been added for search etc are doing that 2006
 * theme. Of a thick border to the left." The app states a choice as a recessed brand key with a
 * lit check, and work that needs a person as an amber dot beside its reason in words
 * (layout-patterns 6). A coloured bar on one edge is neither.
 */
const surfaces = {
    'ExplorerSearch.svelte': searchSource,
    'ExplorerFilters.svelte': filtersSource,
    'DetectionRow.svelte': detectionRowSource,
    'GardenExplorerRow.svelte': gardenExplorerRowSource,
    'FieldLogVisitRow.svelte': fieldLogVisitRowSource,
    'FieldLogGardenRow.svelte': fieldLogGardenRowSource
};

describe('state is never a coloured bar on one edge', () => {
    for (const [name, source] of Object.entries(surfaces)) {
        it(`${name} draws no edge bar`, () => {
            expect(source).not.toMatch(/border-l-\d/);
            expect(source).not.toMatch(/absolute inset-y-0 left-0 w-\[\dpx\]/);
        });
    }
});

describe('a chosen row is a recessed brand key with a lit check', () => {
    it('is defined once in the kit', () => {
        expect(appCss).toMatch(/\.choice-active \{[^}]*bg-brand-50[^}]*\}/);
        expect(appCss).toMatch(/\.choice-active svg \{[^}]*text-brand-600/);
    });

    it('marks the rail rows with the kit class and a check that is not colour alone', () => {
        expect(filtersSource).toContain('choice-active');
        expect(filtersSource).toContain('data-explorer-chosen-mark');
    });

    it('marks the active search result the same way, with an Enter cue that says what Enter does', () => {
        expect(searchSource).toContain('choice-active');
        expect(searchSource).toContain('data-explorer-search-active-cue');
        expect(searchSource).not.toContain('lg:w-96');
    });
});

describe('a row that needs a person carries an amber dot beside its reason in words', () => {
    it('is defined once in the kit, on the attention scale', () => {
        expect(appCss).toMatch(/\.attention-dot \{[^}]*bg-attention-500[^}]*\}/);
    });

    for (const [name, source] of Object.entries({
        'DetectionRow.svelte': detectionRowSource,
        'GardenExplorerRow.svelte': gardenExplorerRowSource,
        'FieldLogVisitRow.svelte': fieldLogVisitRowSource,
        'FieldLogGardenRow.svelte': fieldLogGardenRowSource
    })) {
        it(`${name} keeps the tint faint and puts the dot beside the words`, () => {
            expect(source).toContain('attention-dot');
            expect(source).toContain('bg-attention-500/5');
            expect(source).not.toContain('bg-attention-500/10');
        });
    }
});

describe('the Explorer search is a page control, not a filter', () => {
    it('sits in the header row on a desktop and in the rail on a phone, mounted once', () => {
        expect(eventsSource).toContain("new MediaQuery('min-width: 1024px'");
        expect(eventsSource).toContain('data-explorer-header-search');
        const header = eventsSource.indexOf('data-explorer-header-search');
        const count = eventsSource.indexOf('data-explorer-count');
        expect(header).toBeGreaterThan(-1);
        expect(header).toBeLessThan(count);
        // The rail receives the box only where the header does not hold it.
        expect(eventsSource).toMatch(/search=\{wideExplorer\.current \? undefined : explorerSearch\}/);
        expect(eventsSource.match(/<ExplorerSearch/g)).toHaveLength(1);
    });
});
