import { describe, expect, it } from 'vitest';
import wallSource from './CaptureWall.svelte?raw';
import filmSource from './VisitFilm.svelte?raw';
import filmsSource from '../utils/visit-films.ts?raw';
import portraitSource from './FeederPortrait.svelte?raw';
import aboutSource from '../pages/About.svelte?raw';
import speciesSource from '../pages/Species.svelte?raw';
import privacySource from './PrivacySummary.svelte?raw';
import en from '../i18n/locales/en.json';

describe('the leaderboard opens on a wall of this feeder\'s own visits', () => {
    it('sits above the share bar, every tile a visit that opens its species', () => {
        const wall = speciesSource.indexOf('<CaptureWall');
        expect(wall).toBeGreaterThan(-1);
        expect(wall).toBeLessThan(speciesSource.indexOf('<SpeciesChecks'));
        expect(speciesSource).toContain("{#if sourceMode !== 'heard' && sourceLeader && sourceLeader.count > 0}");
        expect(wallSource).toContain('{#if loading || usable.length >= WALL_MINIMUM}');
        expect(speciesSource).toContain('onopen={(key) => (selectedSpecies = key)}');
        // A tile is the stored photograph (the crop) at card size, never the whole-scene
        // thumbnail and never the multi-megabyte original.
        expect(wallSource).toContain('src={getReelImageUrl(tile.frigateEvent)}');
        expect(wallSource).not.toContain('getSnapshotUrl');
        expect(wallSource).toContain('<button');
        expect(wallSource).toContain('aria-label={tileName(tile)}');
        // The About page no longer carries a reel of its own.
        expect(aboutSource).not.toContain('CaptureWall');
    });

    it('lights the hovered species and dims the rest, on hover and on keyboard focus alike', () => {
        expect(wallSource).toContain('onpointerenter={(event) => hoverTile(event, tile)}');
        expect(wallSource).toContain('onfocus={(event) => focusTile(event, tile)}');
        expect(wallSource).toContain("target.matches(':focus-visible')");
                // Touch has no hover, so a tap opens the species instead of a pop-out.
        expect(wallSource).toContain("event.pointerType === 'touch'");
        // The wall dims only from the share bar: a visit under the pointer is ringed, never resized.
        expect(wallSource).toContain('.wall.has-active .tile:not(.lit)');
        expect(wallSource).not.toContain('transform: scale(1.07)');
    });

    it('opens a pop-out that stays inside the viewport and closes on Escape or scroll', () => {
        expect(wallSource).toContain('role="tooltip"');
        expect(wallSource).toContain('aria-describedby={activeTile === tile.key ? popoutId : undefined}');
        expect(wallSource).toContain("event.key !== 'Escape'");
        expect(wallSource).toContain("window.addEventListener('scroll', follow");
        expect(wallSource).toContain('viewportHeight - height - 8');
        // It can be reached with the pointer, so the text in it can be read (WCAG 1.4.13).
        expect(wallSource).toContain('onpointerenter={holdOpen}');
    });

    it('never leaves a hole: a photograph that fails to load leaves the wall', () => {
        expect(wallSource).toContain('use:photo={() => markFailed(tile.frigateEvent)}');
        expect(wallSource).toContain('.filter((tile) => !failed.has(tile.frigateEvent))');
    });

    it('stands still under reduced motion', () => {
        expect(wallSource).toContain('@media (prefers-reduced-motion: reduce)');
        expect(wallSource).toContain(':global(.reduced-motion) .tile.rising');
        expect(wallSource).toContain('const rising = $derived(!introDone && !reduceMotion);');
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
        expect(aboutSource).toContain('if (portrait?.latest_visit?.frigate_event === frigateEvent) portraitRefresh += 1;');
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
