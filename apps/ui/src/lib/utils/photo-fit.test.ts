import { describe, expect, it } from 'vitest';
import { photoFit, photoFitFor } from './photo-fit';

describe('photoFit', () => {
    it('keeps covering the box for a scene or a square photo, which lose at most a quarter', () => {
        expect(photoFit(1920, 1080, 400, 300)).toBe('cover');
        expect(photoFit(500, 500, 400, 300)).toBe('cover');
        expect(photoFit(800, 600, 400, 300)).toBe('cover');
    });

    it('shows a tall crop whole instead of cutting its middle out', () => {
        // A woodpecker on a pole: covering a 4:3 card would cut away about half of it.
        expect(photoFit(187, 293, 400, 300)).toBe('contain');
        expect(photoFit(210, 281, 400, 300)).toBe('contain');
    });

    it('shows a very wide photo whole too', () => {
        expect(photoFit(3000, 600, 400, 300)).toBe('contain');
    });

    it('falls back to cover until both sizes are known', () => {
        expect(photoFit(0, 0, 400, 300)).toBe('cover');
        expect(photoFit(187, 293, 0, 0)).toBe('cover');
        expect(photoFit(Number.NaN, 293, 400, 300)).toBe('cover');
    });

    it('reads the sizes from a loaded image element', () => {
        const image = { naturalWidth: 187, naturalHeight: 293, clientWidth: 400, clientHeight: 300 } as HTMLImageElement;
        expect(photoFitFor(image)).toBe('contain');
    });
});
