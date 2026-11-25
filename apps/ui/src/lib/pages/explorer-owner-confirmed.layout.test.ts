import { describe, expect, it } from 'vitest';
import eventsSource from './Events.svelte?raw';
import filtersSource from '../components/ExplorerFilters.svelte?raw';
import enVisits from '../i18n/locales/en/visits.json';
import enEvents from '../i18n/locales/en/events.json';
import enGarden from '../i18n/locales/en/garden.json';

describe('the Owner confirmed filter in the Explorer', () => {
    it('is an owner-only choice under Only, named as the badge it matches', () => {
        const only = filtersSource.slice(filtersSource.indexOf('data-explorer-only-facet'));
        const ownerBlock = only.slice(only.indexOf('{#if canSeeHidden}'), only.indexOf('{/if}'));
        expect(ownerBlock).toContain('data-explorer-owner-confirmed-facet');
        expect(ownerBlock).toContain("$_('visits.owner_confirmed', { default: 'Owner confirmed' })");
        expect(ownerBlock).toContain('aria-pressed={ownerConfirmedOnly}');
        expect(ownerBlock).toContain('aria-describedby="explorer-owner-confirmed-hint"');
        expect(enVisits.owner_confirmed).toBe('Owner confirmed');
        expect(enVisits.owner_confirmed_filter_hint).toMatch(/A visit counts when one of its captures was named/);
    });

    it('has a token that clears it and counts toward the Only section', () => {
        expect(filtersSource).toContain("key: 'owner-confirmed'");
        expect(filtersSource).toContain('clear: () => onchange({ ownerConfirmedOnly: false })');
        expect(filtersSource).toContain('[favoritesOnly, audioConfirmedOnly, multipleSpeciesOnly, ownerConfirmedOnly, showHidden]');
    });

    it('is never applied for a visitor, and a sign-out clears it', () => {
        expect(eventsSource).toContain('const ownerConfirmedOnly = $derived(authStore.hasOwnerAccess && ownerConfirmedChosen);');
        expect(eventsSource).toMatch(/if \(authStore\.hasOwnerAccess\) return;\s+if \(ownerConfirmedChosen\) ownerConfirmedChosen = false;/);
    });

    it('reaches the visits, the captures and their count', () => {
        expect(eventsSource).toContain('multipleSpeciesOnly, ownerConfirmedOnly,\n                    requestKey: EVENTS_PAGE_REQUEST_KEYS.visits');
        expect(eventsSource).toContain('ownerConfirmedOnly,\n                    fields: \'list\'');
        expect(eventsSource).toContain('ownerConfirmedOnly,\n                    requestKey: EVENTS_PAGE_REQUEST_KEYS.count');
    });

    it('is cleared by every reset', () => {
        expect(eventsSource.match(/ownerConfirmedChosen = false;/g)).toHaveLength(3);
        expect(eventsSource).toContain('if (next.ownerConfirmedOnly !== undefined) ownerConfirmedChosen = next.ownerConfirmedOnly;');
    });

    it('keeps unfiltered Garden captures and heard calls out of a filtered timeline, and says so', () => {
        expect(eventsSource).toContain('if (favoritesOnly || showHidden || multipleSpeciesOnly || ownerConfirmedOnly || audioConfirmedOnly) {');
        expect(eventsSource).toContain('gardenBlocker(subjects, { speciesFilter, favoritesOnly, showHidden, multipleSpeciesOnly, ownerConfirmedOnly,');
        expect(enEvents.heard.blocked_visit_filter).toContain('Owner confirmed');
        expect(enGarden.explorer.blocked_bird_filter).toContain('Owner confirmed');
        expect(enGarden.explorer.bird_filters_ignored).toContain('Owner confirmed');
    });

    it('re-reads a filtered capture list after a record changes, through the shared rule', () => {
        expect(eventsSource).toContain('if (rereadsAfterRecordChange(view)) scheduleReclassifyCompletionRefresh();');
        expect(eventsSource).toContain('multipleSpeciesOnly, ownerConfirmedOnly, showHidden };');
    });

    it('states the address before a shared clip link returns without a read', () => {
        expect(eventsSource).toMatch(/if \(openedViaShare\) \{[\s\S]{0,160}writeAddress\(\);\s+loading = false;\s+return;/);
    });
});
