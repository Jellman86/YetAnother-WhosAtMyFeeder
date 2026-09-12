import { describe, expect, it } from 'vitest';
import reelSource from './CaptureReel.svelte?raw';
import aboutSource from '../pages/About.svelte?raw';
import privacySource from './PrivacySummary.svelte?raw';
import en from '../i18n/locales/en.json';

describe('the About page opens on this feeder\'s own photographs', () => {
    it('shows one crop per species in a reel, and each card opens the record', () => {
        expect(aboutSource).toContain("import CaptureReel from '../components/CaptureReel.svelte';");
        expect(aboutSource).toContain('<CaptureReel items={showcase} {openingEvent} onopen={openCapture} />');
        expect(aboutSource).toContain('fetchEvents({ eventId: item.frigate_event, limit: 1 })');
        expect(aboutSource).toContain('<DetectionModal');
        expect(aboutSource).toContain('readOnly={!authStore.hasOwnerAccess}');
        // The reel replaces the four loose thumbnails; nothing on the page is a photo you cannot open.
        expect(aboutSource).not.toContain('data-about-photos');
        expect(aboutSource).not.toContain('getThumbnailUrl');
        // The card is the stored photograph (the crop) at card size, never the whole-scene
        // thumbnail and never the multi-megabyte original.
        expect(reelSource).toContain('src={getReelImageUrl(item.frigate_event)}');
        expect(reelSource).not.toContain('getSnapshotUrl');
        expect(reelSource).toContain('<button');
        expect(reelSource).toContain('aria-label={label(item)}');
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

    it('degrades one read at a time: no reel without a count, and no count without a reel', () => {
        expect(aboutSource).toContain('{#if showcase.length > 0}');
        expect(aboutSource).toContain('{#if communityInstalls !== null}');
        expect(aboutSource).toContain('about.stats.feeders');
        expect(aboutSource).toContain('about.opener.caption');
    });

    it('lists the install-count read among what leaves the network', () => {
        expect(privacySource).toContain("key: 'community'");
        // Guests cannot read settings, so the row states what the community read itself reported.
        expect(privacySource).toContain('communityReadEnabled ?? Boolean(settingsStore.settings?.update_check_enabled)');
        expect(aboutSource).toContain('<PrivacySummary {communityReadEnabled} />');
        expect(en.about.outbound.community_desc).toContain('update checks');
        for (const value of JSON.stringify(en.about.opener).match(/"[^"]*"/g) ?? []) {
            expect(value).not.toContain('—');
        }
    });
});
