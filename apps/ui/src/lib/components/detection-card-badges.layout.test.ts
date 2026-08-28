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
describe('detection card overlay badges', () => {
    it('keeps the time and the score together on one row', () => {
        const bottomRow = detectionCardSource.match(/absolute bottom-3 left-3[\s\S]*?\n {12}<\/div>/);
        expect(bottomRow, 'expected the bottom-left overlay row').not.toBeNull();
        expect(bottomRow?.[0]).toContain('formatTime(detection.detection_time)');
        expect(bottomRow?.[0]).toContain('detection.score * 100');
    });

    it('no longer strands the score in the opposite corner', () => {
        expect(detectionCardSource).not.toMatch(/absolute top-3 right-3/);
    });

    it('gives both chips the same type scale, from the constrained scale', () => {
        // `text-[10px]` was an arbitrary value, which the visual standard rules
        // out, and it made the two chips visibly different weights.
        expect(detectionCardSource).not.toContain('text-[10px]');
        const chips = detectionCardSource.match(/class="[^"]*bg-black\/60[^"]*"/g) ?? [];
        expect(chips.length, 'expected the time and score chips').toBeGreaterThanOrEqual(2);
        for (const chip of chips) {
            expect(chip).toContain('text-xs');
            expect(chip).toContain('min-h-11');
        }
    });

    it('never wraps, because a second line lifts the readings off the bottom', () => {
        // The row is anchored to the bottom of the photograph, so wrapping grows
        // it upward. Measured in the real grid: at a 1024px viewport the row
        // wrapped to three lines covering 76% of the picture, and at 1280px to
        // two lines starting halfway down. The narrowest card is not a phone,
        // where a card is full width, but the densest desktop grid.
        expect(detectionCardSource).toMatch(/absolute bottom-3 left-3[^"]*flex-nowrap/);
        expect(detectionCardSource).not.toMatch(/absolute bottom-3 left-3[^"]*flex-wrap/);
    });

    it('keeps a card wide enough for that one line', () => {
        // Four columns beside the 14rem filter rail gave a 168px card at 1024px,
        // which is narrower than the row it has to carry.
        expect(eventsPageSource).toContain('md:grid-cols-3 2xl:grid-cols-4');
        expect(eventsPageSource).not.toContain('lg:grid-cols-4 gap-4');
    });

    it('marks a ready full-visit clip on the play button, not beside it', () => {
        // A 20px circle next to a 44px one read as a second, broken control, and
        // it cost the row 28px it did not have.
        expect(detectionCardSource).toContain('absolute -right-0.5 -top-0.5');
        expect(detectionCardSource).not.toMatch(/inline-flex h-5 w-5[^"]*bg-brand-500\/90/);
    });
});
