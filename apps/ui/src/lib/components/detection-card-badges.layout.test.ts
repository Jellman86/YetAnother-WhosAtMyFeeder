import { describe, expect, it } from 'vitest';
import detectionCardSource from './DetectionCard.svelte?raw';
import eventsPageSource from '../pages/Events.svelte?raw';

/**
 * #267: "The score badge is placed top left while all the others are at the
 * bottom. Also it has a very big difference is size compared to the others."
 *
 * The side was misremembered — it sat top-right — but the substance held: the
 * score sat alone in the opposite corner from the time, one notch larger, so a
 * card showed its two facts diagonally apart at two different weights.
 */
describe('detection card readings', () => {
    const readings = detectionCardSource.slice(detectionCardSource.indexOf('data-detection-card-readings'));

    it('keeps the time and the score together on one line in the card body, off the photograph', () => {
        // Round 4: chips over every photograph made the grid busy and covered the bird
        // (layout-patterns §5: only the favourite star sits on the image).
        expect(readings).toContain('formatTime(detection.detection_time)');
        expect(readings).toContain('detection.score * 100');
        expect(detectionCardSource).not.toMatch(/absolute bottom-3 left-3/);
        expect(detectionCardSource).not.toContain('photo-chip');
    });

    it('leaves only the favourite star on the photograph', () => {
        const photo = detectionCardSource.slice(detectionCardSource.indexOf('<!-- Image Section -->'), detectionCardSource.indexOf('<!-- Body -->'));
        expect(photo).toContain('detection.is_favorite');
        for (const mark of ['ownerConfirmation', 'isVerified', 'hasAudioConfirmed', 'manual_upload', 'upstreamMissing', 'canPlayVideo']) {
            expect(photo, mark).not.toContain(`{#if ${mark}`);
        }
        expect(readings).toContain('{#if canPlayVideo}');
        expect(readings).toContain('{#if upstreamMissing}');
    });

    it('no longer strands the score in the opposite corner', () => {
        expect(detectionCardSource).not.toMatch(/absolute top-3 right-3/);
    });

    it('sets the readings on the constrained scale, each a 44px target with its explanation', () => {
        expect(detectionCardSource).not.toContain('text-[10px]');
        const chips = readings.match(/<BadgeHint text=[^>]*class="[^"]*"/g) ?? [];
        expect(chips.length, 'expected the time and score readings').toBeGreaterThanOrEqual(2);
        for (const chip of chips) {
            expect(chip).toContain('text-xs');
            expect(chip).toContain('min-h-11');
        }
    });

    it('keeps a card wide enough for that one line, at every width', () => {
        // Fixed column counts could not keep the promise: with the sidebar and
        // the filter rail open, the three-column range at 768-1279px measured
        // 141-227px cards against a row needing ~219px in 12-hour locales, and
        // the card's overflow-hidden clipped the play button entirely. A
        // minimum card width makes the guarantee structural instead of a
        // breakpoint-by-breakpoint hope.
        // min() lets a phone narrower than the minimum, at the largest text, hold one full-width card.
        expect(eventsPageSource).toContain('grid-cols-[repeat(auto-fill,minmax(min(16rem,100%),1fr))]');
        expect(eventsPageSource).not.toMatch(/md:grid-cols-3|2xl:grid-cols-4/);
    });

    it('marks a ready full-visit clip on the play button, not beside it', () => {
        // A 20px circle next to a 44px one read as a second, broken control, and
        // it cost the row 28px it did not have.
        expect(detectionCardSource).toContain('absolute -right-0.5 -top-0.5');
        expect(detectionCardSource).not.toMatch(/inline-flex h-5 w-5[^"]*bg-brand-500\/90/);
    });
});
