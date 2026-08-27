import { describe, expect, it } from 'vitest';
import detectionCardSource from './DetectionCard.svelte?raw';

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

    it('lets the row wrap rather than overflow a narrow card', () => {
        // Time, score and a play button on one line is close to the width of a
        // phone-sized card, so the row wraps instead of running off the edge.
        expect(detectionCardSource).toMatch(/absolute bottom-3 left-3[^"]*flex-wrap/);
    });
});
