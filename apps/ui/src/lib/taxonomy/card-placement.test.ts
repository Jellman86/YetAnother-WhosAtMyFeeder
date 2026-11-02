import { describe, expect, it } from 'vitest';
import { placeCard, type Box } from './card-placement';

// A family-tree dialog inside a 1280 by 860 window: the card must stay inside it, not the window.
const DIALOG: Box = { left: 136, top: 44, right: 1144, bottom: 816 };
const CARD = { width: 320, height: 300 };
const node = (x: number, y: number): Box => ({ left: x - 8, top: y - 8, right: x + 8, bottom: y + 8 });
const inside = (placed: { left: number; top: number; maxHeight: number }, height: number, bounds: Box, margin = 8) => {
    const bottom = placed.top + Math.min(height, placed.maxHeight);
    return placed.left >= bounds.left + margin && placed.left + CARD.width <= bounds.right - margin
        && placed.top >= bounds.top + margin && bottom <= bounds.bottom - margin;
};

describe('a taxon card is placed inside its container without covering its name', () => {
    it('goes below the name when it fits there, centred on it', () => {
        const placed = placeCard(node(527, 200), CARD, DIALOG);
        expect(placed).toEqual({ left: 367, top: 216, maxHeight: 592 });
    });

    it('goes above when the room below the name is inside the window but outside the dialog', () => {
        const placed = placeCard(node(527, 600), CARD, DIALOG);
        expect(placed.top + CARD.height).toBeLessThanOrEqual(600 - 8);
        expect(inside(placed, CARD.height, DIALOG)).toBe(true);
    });

    it('goes beside, on the roomier side, when it fits neither above nor below', () => {
        const tall = { width: 320, height: 520 };
        const placed = placeCard(node(527, 400), tall, DIALOG);
        expect(placed.left).toBe(527 + 8 + 8);
        expect(inside(placed, tall.height, DIALOG)).toBe(true);
        const nearRight = placeCard(node(1000, 400), tall, DIALOG);
        expect(nearRight.left + tall.width).toBe(1000 - 8 - 8);
    });

    it('scrolls inside on the roomier side when nothing else fits, never past the container', () => {
        const narrow: Box = { left: 0, top: 0, right: 390, bottom: 640 };
        const tall = { width: 320, height: 700 };
        const placed = placeCard(node(120, 420), tall, narrow);
        expect(placed.top + placed.maxHeight).toBeLessThanOrEqual(420 - 8 - 8);
        expect(placed.top).toBeGreaterThanOrEqual(8);
        expect(placed.left).toBeGreaterThanOrEqual(8);
        expect(placed.left + tall.width).toBeLessThanOrEqual(390 - 8);
    });

    it('keeps a card wider than its container at the container’s left margin', () => {
        const placed = placeCard(node(150, 100), { width: 400, height: 100 }, { left: 0, top: 0, right: 320, bottom: 600 });
        expect(placed.left).toBe(8);
    });
});
