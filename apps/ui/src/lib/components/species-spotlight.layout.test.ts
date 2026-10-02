import { describe, expect, it } from 'vitest';
import spotlightSource from './SpeciesSpotlight.svelte?raw';
import leaderboardSource from '../pages/Species.svelte?raw';
import en from '../i18n/locales/en.json';

describe('the leaderboard spotlight', () => {
    it('replaces the expanded-view showcase on the leaderboard', () => {
        expect(leaderboardSource).toContain("import SpeciesSpotlight from '../components/SpeciesSpotlight.svelte'");
        expect(leaderboardSource).not.toContain('SpeciesShowcase');
        expect(spotlightSource).toContain('data-leaderboard-spotlight');
        // The photographs cover the list and the flagged species named beneath it.
        expect(leaderboardSource).toContain('fetchLeaderboardPortraits(requestedSpan, controller.signal, SPOTLIGHT_PORTRAITS)');
    });

    it('never enlarges a crop past half again its stored size', () => {
        // Feeder crops are small; stretching one to fill a hero is what made it soft.
        expect(spotlightSource).toContain('const MAX_UPSCALE = 1.5;');
        expect(spotlightSource).toContain('Math.min(stageWidth / size.w, stageHeight / size.h, MAX_UPSCALE)');
        expect(spotlightSource).toContain("return 'max-width: 100%; max-height: 100%;'");
    });

    it('says where every photograph came from', () => {
        expect(spotlightSource).toContain("return { url: withAuthParams(row.photo), source: 'feeder', raw: row.photo }");
        expect(spotlightSource).toContain("return { url: row.reference, source: 'reference', raw: row.reference }");
        expect(spotlightSource).toContain('data-spotlight-reference-note');
        expect(spotlightSource).toContain("data-photo-source={picture?.source ?? 'none'}");
        expect(en.leaderboard.spotlight_no_photo).toBe('No photo from this feeder yet');
        expect(en.leaderboard.showcase_reference.toLowerCase()).toContain('not from this feeder');
    });

    it('keeps probable misidentifications out of the tour and names them apart for a person to check', () => {
        expect(spotlightSource).toContain('const groups = $derived(spotlightGroups(rows));');
        expect(spotlightSource).toContain('{#each groups.checks as row (row.key)}');
        expect(spotlightSource).toContain('data-spotlight-checks');
        expect(en.leaderboard.spotlight_needs_check).toBe('Needs a check');
        // Ranks are the table's, so a species brought forward is named the way the table names it.
        expect(spotlightSource).toContain('{selected.rank === 1 ? eyebrow : rankEyebrow(selected.rank)}');
    });

    it('tours only where motion is welcome, and stops for a person', () => {
        expect(spotlightSource).toContain('const touring = $derived(tourOn && !reduceMotion && tourRows.length > 1);');
        expect(spotlightSource).toContain("classList.contains('reduced-motion')");
        expect(spotlightSource).toContain('@media (prefers-reduced-motion: reduce)');
        // A choice ends the tour; a pointer or focus on the spotlight rests it.
        expect(spotlightSource).toMatch(/function choose\(key: string\): void \{\s*chosenKey = key;\s*tourOn = false;/);
        expect(spotlightSource).toContain("style:animation-play-state={held ? 'paused' : 'running'}");
        expect(spotlightSource).toContain('onanimationend={advance}');
        // A pause control, as WCAG 2.2.2 asks of anything that moves on its own.
        expect(spotlightSource).toContain('data-spotlight-tour');
        // Not announced while it tours; announced once someone chooses.
        expect(spotlightSource).toContain("aria-live={touring ? 'off' : 'polite'}");
    });

    it('draws presence from the timeline it already has, and only presence', () => {
        expect(leaderboardSource).toContain('presenceFor={(row) => presenceFor(row.names, timeline)}');
        expect(spotlightSource).toContain('data-spotlight-presence');
        expect(en.leaderboard.spotlight_presence_days).toBe('On camera on {count} of {total} days');
        // A species keeps the colour the timeline and composition charts give it.
        expect(leaderboardSource).toContain('colourFor={(key) => speciesSeriesColor(speciesSlot().get(key) ?? SPECIES_SERIES_SLOTS, isDark())}');
    });
});
