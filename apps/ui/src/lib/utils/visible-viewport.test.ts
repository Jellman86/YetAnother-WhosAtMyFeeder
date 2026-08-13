import { describe, expect, it } from 'vitest';

import { intersectVisibleViewport } from './visible-viewport';

describe('intersectVisibleViewport', () => {
    it('limits a full-height modal to the space above a mobile keyboard', () => {
        expect(
            intersectVisibleViewport(
                { top: 0, height: 800 },
                { offsetTop: 0, height: 476 }
            )
        ).toEqual({ top: 0, height: 476 });
    });

    it('accounts for browser chrome shifting the visible viewport', () => {
        expect(
            intersectVisibleViewport(
                { top: 0, height: 800 },
                { offsetTop: 64, height: 412 }
            )
        ).toEqual({ top: 64, height: 412 });
    });

    it('keeps the modal bounds when the visual viewport fully contains it', () => {
        expect(
            intersectVisibleViewport(
                { top: 40, height: 720 },
                { offsetTop: 0, height: 800 }
            )
        ).toEqual({ top: 0, height: 720 });
    });

    it('returns an empty intersection when the modal is outside the visible viewport', () => {
        expect(
            intersectVisibleViewport(
                { top: 700, height: 100 },
                { offsetTop: 0, height: 600 }
            )
        ).toEqual({ top: 0, height: 0 });
    });
});
