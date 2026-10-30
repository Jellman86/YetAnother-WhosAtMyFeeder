import { describe, expect, it } from 'vitest';
import eventsSource from './Events.svelte?raw';
import rowSource from '../components/GardenExplorerRow.svelte?raw';
import cardSource from '../components/GardenExplorerCard.svelte?raw';
import modalSource from '../components/GardenCaptureModal.svelte?raw';
import markerSource from '../components/GardenExplorerMarker.svelte?raw';
import filtersSource from '../components/ExplorerFilters.svelte?raw';
import en from '../i18n/locales/en.json';

describe('Garden captures in the Explorer', () => {
    it('shows them only to an owner with the Garden beta on, and lets that owner choose birds, Garden or both', () => {
        expect(eventsSource).toContain("authStore.hasOwnerAccess && settingsStore.settings?.beta_garden_animals === true");
        expect(eventsSource).toContain("gardenAvailable ? explorerSubjectsStore.value : 'birds'");
        // A filter in the rail, with its own token, like every other filter.
        expect(eventsSource).toContain('{gardenAvailable}');
        expect(filtersSource).toContain('data-explorer-visitors-facet');
        expect(filtersSource).toContain('aria-pressed={chosen}');
        expect(filtersSource).toContain("key: 'subjects'");
        expect(filtersSource).toContain('data-explorer-garden-review-facet');
        expect(en.garden.explorer.subjects_garden_visitors).toBe('Garden visitors');
        expect(en.garden.explorer.subjects_birds).toBe('Birds');
    });

    it('places captures between visits in both layouts and opens the Garden record, not the bird one', () => {
        expect(eventsSource).toContain('placeGardenCaptures(birdEntries, entryTime, leads');
        // One animal's stay is one entry, as a bird's is; unconfirmed motion proposals stack by position.
        expect(eventsSource).toContain('fetchGardenVisits({');
        expect(eventsSource).not.toContain('groupGardenVisits(shownGarden)');
        expect(eventsSource).toContain('<GardenExplorerRow capture={entry.capture}');
        expect(eventsSource).toContain('<GardenExplorerCard capture={entry.capture}');
        expect(eventsSource).toContain('<GardenCaptureModal\n        capture={selectedGarden}');
        expect(eventsSource).toContain('group={selectedGardenVisit?.items ?? [selectedGarden]}');
    });

    it('says in words why captures are hidden, instead of mixing filtered visits with unfiltered animals', () => {
        expect(eventsSource).toContain('data-explorer-garden-notice');
        expect(en.garden.explorer.blocked_bird_filter).toMatch(/only describe bird visits/);
        expect(en.garden.explorer.load_failed).toMatch(/visits are unaffected/);
        expect(eventsSource).toContain('data-explorer-garden-empty');
    });

    it('marks every entry Garden in words and states the work a person owes', () => {
        expect(markerSource).toContain("garden.explorer.marker");
        for (const source of [rowSource, cardSource]) {
            expect(source).toContain('<GardenExplorerMarker');
            expect(source).toContain('text.state');
            expect(source).toContain('view.review');
        }
        // Amber means a person is needed in every theme; accent is a brand colour (layout-patterns 1.3).
        // That amber is the attention-* scale, which no theme repaints.
        expect(rowSource).toContain('bg-attention-500/10');
        for (const source of [rowSource, cardSource, modalSource]) expect(source).not.toMatch(/accent-\d/);
        expect(en.garden.explorer.state_presence).toMatch(/Needs review/);
    });

    it('keeps bird-only actions out of the Garden record and states what each decision does', () => {
        for (const birdAction of ['reclassify', 'VideoPlayer', 'audio_confirmed', 'onReclassify']) {
            expect(modalSource).not.toContain(birdAction);
        }
        expect(modalSource).toContain('role="dialog"');
        expect(modalSource).toContain('trapFocus(dialog)');
        expect(modalSource).toContain('lockDocumentScroll()');
        expect(modalSource).toContain("event.key === 'Escape'");
        expect(en.garden.explorer.confirm_name).toBe('Confirm {name}');
    });

    it("orders the rail as the bird record does and dismisses from the bird's bottom row", () => {
        const at = (marker: string): number => {
            const index = modalSource.indexOf(marker);
            expect(index, marker).toBeGreaterThan(-1);
            return index;
        };
        // Facts, the family tree, the species, then the decisions, then hide-style dismissal, then Details.
        expect(at('data-garden-capture-facts')).toBeLessThan(at('<TaxonomyLineage'));
        expect(at('<TaxonomyLineage')).toBeLessThan(at('data-garden-species-info'));
        expect(at('data-garden-species-info')).toBeLessThan(at('data-garden-capture-actions'));
        expect(at('data-garden-capture-actions')).toBeLessThan(at('data-garden-capture-bottom-actions'));
        expect(at('data-garden-capture-bottom-actions')).toBeLessThan(at('data-garden-capture-details'));
        expect(modalSource).toContain('subject="animal"');
        expect(modalSource).toContain("actions.pick_species");
        // The dismiss control is the bird record's hide tile, named by its effect rather than explained beneath.
        const bottomRow = modalSource.slice(at('data-garden-capture-bottom-actions'), at('data-garden-capture-details'));
        // As a bird's hide control hides its visit, the tile dismisses the whole entry; one capture goes beside its photo.
        expect(bottomRow).toContain('data-garden-entry-dismiss');
        expect(bottomRow).toContain('onclick={dismissEntry}');
        expect(bottomRow).not.toContain('data-garden-capture-dismiss');
        expect(at('data-garden-capture-group')).toBeLessThan(at('data-garden-capture-dismiss'));
        expect(at('data-garden-capture-dismiss')).toBeLessThan(at('data-garden-capture-rail'));
        for (const retired of ['dismiss_effect', 'group_dismiss_help', 'visit_dismiss_help', 'garden.group_review', 'check_effect', 'manual_suggestion_help']) {
            expect(modalSource).not.toContain(retired);
        }
    });

    it("follows the bird record's shape and the bird row's alignment", () => {
        // Photograph full-bleed on a dark column with the subject over it, close floating, facts in rows.
        expect(modalSource).toContain('data-garden-capture-media');
        expect(modalSource).toContain('lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]');
        expect(modalSource).toContain('data-garden-capture-facts');
        expect(modalSource).toContain("detection.fact_species_match");
        // A row's name starts where a bird's does; the marker leads the line beneath it.
        expect(rowSource.indexOf('{text.title}')).toBeLessThan(rowSource.indexOf('<GardenExplorerMarker compact />'));
    });

    it('writes its copy without em dashes', () => {
        for (const value of Object.values(en.garden.explorer)) expect(value).not.toContain('—');
    });
});
