import { describe, expect, it } from 'vitest';
import eventsSource from './Events.svelte?raw';
import rowSource from '../components/GardenExplorerRow.svelte?raw';
import cardSource from '../components/GardenExplorerCard.svelte?raw';
import modalSource from '../components/GardenCaptureModal.svelte?raw';
import markerSource from '../components/GardenExplorerMarker.svelte?raw';
import en from '../i18n/locales/en.json';

describe('Garden captures in the Explorer', () => {
    it('shows them only to an owner with the Garden beta on, and lets that owner choose birds, Garden or both', () => {
        expect(eventsSource).toContain("authStore.hasOwnerAccess && settingsStore.settings?.beta_garden_animals === true");
        expect(eventsSource).toContain("gardenAvailable ? explorerSubjectsStore.value : 'birds'");
        expect(eventsSource).toContain('data-explorer-subjects');
        expect(eventsSource).toContain('aria-pressed={subjects === option.value}');
        expect(en.garden.explorer.subjects_birds).toBe('Birds');
        expect(en.garden.explorer.subjects_all).toBe('All');
    });

    it('places captures between visits in both layouts and opens the Garden record, not the bird one', () => {
        expect(eventsSource).toContain('placeGardenCaptures(birdEntries, entryTime, shownGarden');
        expect(eventsSource).toContain('<GardenExplorerRow capture={entry.capture}');
        expect(eventsSource).toContain('<GardenExplorerCard capture={entry.capture}');
        expect(eventsSource).toContain('<GardenCaptureModal capture={selectedGarden}');
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
        expect(rowSource).toContain('bg-amber-500/10');
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
        expect(en.garden.explorer.dismiss_effect).toMatch(/removes it from the Explorer/);
    });

    it('writes its copy without em dashes', () => {
        for (const value of Object.values(en.garden.explorer)) expect(value).not.toContain('—');
    });
});
