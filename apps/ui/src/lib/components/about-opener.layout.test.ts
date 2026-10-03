import { describe, expect, it } from 'vitest';
import reelSource from './CaptureReel.svelte?raw';
import filmSource from './VisitFilm.svelte?raw';
import filmsSource from '../utils/visit-films.ts?raw';
import portraitSource from './FeederPortrait.svelte?raw';
import aboutSource from '../pages/About.svelte?raw';
import speciesSource from '../pages/Species.svelte?raw';
import privacySource from './PrivacySummary.svelte?raw';
import en from '../i18n/locales/en.json';

describe('the leaderboard opens on this feeder\'s own photographs', () => {
    it('sits above the share bar, one card per leading species, each opening the species', () => {
        const reel = speciesSource.indexOf('<CaptureReel');
        expect(reel).toBeGreaterThan(-1);
        expect(reel).toBeLessThan(speciesSource.indexOf('<SpeciesShareBar'));
        expect(speciesSource).toContain("{#if sourceMode !== 'heard' && leaderboardReel.length > 0}");
        expect(speciesSource).toContain('onopen={(card) => (selectedSpecies = card.key)}');
        // The card is the stored photograph (the crop) at card size, never the whole-scene
        // thumbnail and never the multi-megabyte original.
        expect(reelSource).toContain('poster={getReelImageUrl(card.frigateEvent)}');
        expect(reelSource).not.toContain('getSnapshotUrl');
        expect(reelSource).toContain('<button');
        expect(reelSource).toContain('aria-label={card.label}');
        // The About page no longer carries a reel of its own.
        expect(aboutSource).not.toContain('CaptureReel');
    });

    it('loops with decorative copies that readers and the Tab key never meet', () => {
        expect(reelSource).toContain('{#each copiesFor(rowIndex) as loop, copyIndex (copyIndex)}');
        expect(reelSource).toContain('aria-hidden={loop}');
        expect(reelSource).toContain('tabindex={loop ? -1 : 0}');
        // The drift moves by one measured copy, and the row is covered however wide the screen
        // is: a short row shifted by half its track would drift into empty space.
        expect(reelSource).toContain('Math.ceil(rowWidth / setWidth) + 1');
        expect(reelSource).toContain('transform: translateX(var(--reel-shift, -50%));');
    });

    it('answers hover and press on every card, and a click never makes the row jump', () => {
        expect(reelSource).toContain('hover:-translate-y-1 hover:border-brand-400/70 hover:shadow-xl active:translate-y-0 active:scale-[0.98]');
        expect(reelSource).toContain('group-hover:scale-[1.04]');
        // A click focuses the card, but only keyboard focus (:focus-visible) stills the reel;
        // stilling it on a click drops the drift's transform and the whole row jumps.
        expect(reelSource).toContain('if (!isKeyboardFocus(target)) return;');
        expect(reelSource).toContain("target.matches(':focus-visible')");
    });

    it('stands still and scrolls while keyboard focus is inside it, so no focused card is hidden', () => {
        expect(reelSource).toContain('onfocusin={handleFocusIn}');
        expect(reelSource).toContain("target.scrollIntoView({ block: 'nearest', inline: 'nearest' })");
        expect(reelSource).toContain('.reel.still .track');
        expect(reelSource).toContain(".reel.still .set[aria-hidden='true']");
    });

    it('pauses under the pointer or focus, and stands still for reduced motion', () => {
        expect(reelSource).toContain('.reel:hover .track,\n    .reel:focus-within .track {\n        animation-play-state: paused;');
        expect(reelSource).toContain('@media (prefers-reduced-motion: reduce)');
        expect(reelSource).toContain(':global(.reduced-motion) .track');
        // With no drift the loop copy would be a duplicate list, so it goes and the row scrolls.
        expect(reelSource).toContain(".set[aria-hidden='true'] {\n            display: none;");
        expect(reelSource).toContain('overflow-x: auto;');
    });
});

describe('a visit film', () => {
    it('is a photograph first: the film plays over it only once made, visible, and allowed to move', () => {
        expect(filmSource).toContain('<img src={poster} alt=""');
        expect(filmSource).toContain('if (!near || !film || still) return;');
        expect(filmSource).toContain("document.documentElement.classList.contains('reduced-motion')");
        expect(filmSource).toContain('connection?.saveData === true');
        expect(filmSource).toContain('video.pause();');
        // Silent decoration over a labelled card: never announced, never a Tab stop.
        expect(filmSource).toContain('muted');
        expect(filmSource).toContain('playsinline');
        expect(filmSource).toContain('aria-hidden="true"');
        expect(filmSource).toContain('tabindex="-1"');
    });

    it('is downloaded once however many copies of a card show it, and released with the last', () => {
        expect(filmsSource).toContain('entry.holders += 1;');
        expect(filmsSource).toContain('if (entry.holders > 0) return;');
        expect(filmsSource).toContain('URL.revokeObjectURL(url)');
        expect(filmsSource).toContain('entry.controller.abort();');
    });
});

describe('the About page opens on a portrait of this feeder', () => {
    it('states measured facts beside the latest visit, which opens its record', () => {
        expect(aboutSource).toContain("import FeederPortrait from '../components/FeederPortrait.svelte';");
        expect(aboutSource).toContain('fetchEvents({ eventId: frigateEvent, limit: 1 })');
        expect(aboutSource).toContain('<DetectionModal');
        expect(aboutSource).toContain('readOnly={!authStore.hasOwnerAccess}');
        expect(portraitSource).toContain('onclick={() => onopenvisit(latest.frigate_event)}');
        expect(portraitSource).toContain('film={Boolean(latest.film_url)}');
        // The newest arrival opens the species by the label the history stores.
        expect(portraitSource).toContain('onopenspecies(arrival.species)');
    });

    it('tells a guest the facts cover the shared window, so a short window never reads as a young feeder', () => {
        expect(portraitSource).toContain("if (portrait.scope === 'shared')");
        expect(en.about.portrait.shared_days).toBe('The last {days} days at this feeder.');
        expect(en.about.portrait.since).toBe('Watching since {date}.');
    });

    it('reads the busiest day as a calendar date, so no time zone moves it', () => {
        expect(portraitSource).toContain('formatDate(`${portrait.busiest_day.date}T12:00:00`)');
    });

    it('degrades one read at a time: no portrait is still an About page', () => {
        expect(aboutSource).toContain('{#if portrait}');
        expect(portraitSource).toContain('{#if communityInstalls !== null}');
        expect(portraitSource).toContain('about.portrait.community');
        // The latest visit gone (deleted or hidden) moves the portrait on.
        expect(aboutSource).toContain('if (portrait?.latest_visit?.frigate_event === frigateEvent) void loadPortrait();');
    });

    it('lists the install-count read among what leaves the network', () => {
        expect(privacySource).toContain("key: 'community'");
        // Guests cannot read settings, so the row states what the community read itself reported.
        expect(privacySource).toContain('communityReadEnabled ?? Boolean(settingsStore.settings?.update_check_enabled)');
        expect(aboutSource).toContain('<PrivacySummary {communityReadEnabled} />');
        expect(en.about.outbound.community_desc).toContain('update checks');
        for (const value of JSON.stringify(en.about.portrait).match(/"[^"]*"/g) ?? []) {
            expect(value).not.toContain('—');
        }
    });
});
