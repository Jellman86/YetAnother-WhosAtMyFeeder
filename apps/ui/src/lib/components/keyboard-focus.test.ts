import { describe, expect, it } from 'vitest';
import historyStepSource from './setup/HistoryStep.svelte?raw';
import speciesDetailModalSource from './SpeciesDetailModal.svelte?raw';

/**
 * #266 was reported as "the live feed button does not work". It was not a
 * button — it was a status pill, and the reporter's own follow-up named the
 * real problem: "it is not always clear what is clickable and what is not".
 *
 * The elements in their screenshot are gone with the rebuilt dashboard, but
 * auditing the principle against current code found the sharper version of the
 * same complaint: controls a keyboard user cannot see they have reached.
 */
describe('a control must show when it has keyboard focus', () => {
    it('shows focus on the setup history range options', () => {
        // The radio is `sr-only`, so its native outline is invisible, and the
        // styled span never receives focus itself — `focus-ring` on it can
        // never fire. Without a peer rule there is no focus indicator at all,
        // which fails the WCAG 2.2 AA floor the UI standard sets.
        expect(historyStepSource).toContain('peer sr-only');
        expect(historyStepSource).toMatch(/peer-focus-visible:/);
    });

    it('shows focus on a source link styled as a badge', () => {
        // `.badge` carries no focus styling, so a link wearing it falls back to
        // the browser default and looks nothing like every other control.
        const badgeLink = speciesDetailModalSource.match(/<a[^>]*class="badge[^"]*"/s);
        expect(badgeLink, 'expected a badge-styled link to audit').not.toBeNull();
        expect(badgeLink?.[0]).toMatch(/focus-ring|focus-visible:/);
    });
});
