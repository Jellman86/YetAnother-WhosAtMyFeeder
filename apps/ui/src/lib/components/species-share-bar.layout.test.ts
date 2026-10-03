import { describe, expect, it } from 'vitest';
import shareSource from './SpeciesShareBar.svelte?raw';
import leaderboardSource from '../pages/Species.svelte?raw';
import en from '../i18n/locales/en.json';

describe('the leaderboard share bar', () => {
    it('sits under the reel in place of the old photo spotlight, which the reel replaced', () => {
        expect(leaderboardSource).toContain("import SpeciesShareBar from '../components/SpeciesShareBar.svelte'");
        expect(leaderboardSource).not.toContain('SpeciesSpotlight');
        expect(shareSource).toContain('data-leaderboard-share');
        // No large photograph, tour or second ranked list: the reel shows the photographs and the
        // rankings table below lists the species.
        expect(shareSource).not.toContain('data-spotlight-stage');
        expect(shareSource).not.toContain('data-spotlight-list');
        expect(shareSource).not.toContain('tourOn');
        // The photographs cover the reel and the flagged species named beneath the bar.
        expect(leaderboardSource).toContain('fetchLeaderboardPortraits(requestedSpan, controller.signal, SPOTLIGHT_PORTRAITS)');
    });

    it('says where every photograph came from', () => {
        expect(shareSource).toContain("return { url: withAuthParams(row.photo), source: 'feeder', raw: row.photo }");
        expect(shareSource).toContain("return { url: row.reference, source: 'reference', raw: row.reference }");
        expect(en.leaderboard.spotlight_no_photo).toBe('No photo from this feeder yet');
        expect(en.leaderboard.showcase_reference.toLowerCase()).toContain('not from this feeder');
    });

    it('names probable misidentifications apart for a person to check', () => {
        expect(shareSource).toContain('const groups = $derived(spotlightGroups(rows));');
        expect(shareSource).toContain('{#each groups.checks as row (row.key)}');
        expect(shareSource).toContain('data-spotlight-checks');
        expect(en.leaderboard.spotlight_needs_check).toBe('Needs a check');
    });

    it('names each segment of the bar in a pop-out that follows the hover contract', () => {
        // A hovering pointer or keyboard focus opens it, never a touch replay; a tap opens the species.
        expect(shareSource).toContain("if (event.pointerType !== 'touch') openPopout(segment.key, event.currentTarget);");
        expect(shareSource).toContain("if (event.currentTarget.matches(':focus-visible')) openPopout(segment.key, event.currentTarget);");
        expect(shareSource).toContain("if (kind === 'species') onopen(key);");
        expect(shareSource).toContain('const POPOUT_GRACE_MS = 120;');
        expect(shareSource).toContain('onpointerenter={cancelPopoutClose}');
        expect(shareSource).toContain("if (event.key === 'Escape' && openKey !== null)");
        expect(shareSource).toContain('aria-expanded={openKey === segment.key}');
        expect(shareSource).toContain('role="tooltip"');
        // Common and scientific name over the species' stock photograph, labelled with its source.
        expect(shareSource).toContain('{popout.row.displayName}');
        expect(shareSource).toContain('{popout.row.subName}');
        expect(shareSource).toContain('const stock = stockPictureFor(popout.row)');
        expect(shareSource).toContain('data-spotlight-popout-source');
        expect(shareSource).toContain(':global(.reduced-motion) .spotlight-popout');
    });

    it('keeps each species in the colour the timeline and composition charts give it', () => {
        expect(leaderboardSource).toContain('colourFor={(key) => speciesSeriesColor(speciesSlot().get(key) ?? SPECIES_SERIES_SLOTS, isDark())}');
        expect(shareSource).toContain("classList.contains('reduced-motion')");
    });
});
