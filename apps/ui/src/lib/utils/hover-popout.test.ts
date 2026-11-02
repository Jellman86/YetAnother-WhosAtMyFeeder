import { describe, expect, it } from 'vitest';
import { POPOUT_CLOSE_GRACE_MS, popoutAnchor } from './hover-popout.svelte';

const viewport = { width: 1280, height: 800 };
const panel = { width: 240, estimatedHeight: 220 };

describe('hover pop-out placement', () => {
    it('opens beneath its thumbnail, centred on it, when there is room', () => {
        expect(popoutAnchor({ top: 100, bottom: 144, left: 400, width: 44 }, viewport, panel)).toEqual({ x: 422, y: 152, above: false });
    });

    it('flips above a thumbnail near the foot of the window rather than running off it', () => {
        expect(popoutAnchor({ top: 700, bottom: 744, left: 400, width: 44 }, viewport, panel)).toEqual({ x: 422, y: 692, above: true });
    });

    it('keeps the whole panel inside the window at either edge', () => {
        expect(popoutAnchor({ top: 100, bottom: 144, left: 0, width: 44 }, viewport, panel).x).toBe(128);
        expect(popoutAnchor({ top: 100, bottom: 144, left: 1260, width: 44 }, viewport, panel).x).toBe(1152);
    });

    it('waits long enough for a pointer to cross into the panel (WCAG 2.2 SC 1.4.13)', () => {
        expect(POPOUT_CLOSE_GRACE_MS).toBe(120);
    });
});
