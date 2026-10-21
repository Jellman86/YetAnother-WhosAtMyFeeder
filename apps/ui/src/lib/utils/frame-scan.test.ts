import { describe, expect, it } from 'vitest';

import { frameScan } from './frame-scan';

function progress(overrides: Partial<Parameters<typeof frameScan>[0]> = {}): Parameters<typeof frameScan>[0] {
    return { currentFrame: 0, totalFrames: 4, frameResults: [], status: 'running', ...overrides };
}

describe('frameScan', () => {
    it('shows every frame as waiting before the first result arrives', () => {
        const scan = frameScan(progress());

        expect(scan.bars.map((bar) => bar.tone)).toEqual(['pending', 'pending', 'pending', 'pending']);
        expect(scan.readCount).toBe(0);
        expect(scan.latest).toBeNull();
        expect(scan.best).toBeNull();
        expect(scan.nextPosition).toBe(1);
    });

    it('grades each read frame by confidence and draws its height from the score', () => {
        const scan = frameScan(progress({
            currentFrame: 3,
            frameResults: [
                { label: 'Blue Tit', score: 0.91 },
                { label: 'Blue Tit', score: 0.62 },
                { label: 'Background', score: 0.2 }
            ]
        }));

        expect(scan.bars.map((bar) => bar.tone)).toEqual(['strong', 'moderate', 'weak', 'pending']);
        expect(scan.bars.map((bar) => bar.heightPercent)).toEqual([91, 62, 20, 0]);
        expect(scan.readCount).toBe(3);
        expect(scan.nextPosition).toBe(4);
    });

    it('keeps a very low score visible as a short bar rather than an empty slot', () => {
        const scan = frameScan(progress({ currentFrame: 1, frameResults: [{ label: 'Background', score: 0.01 }] }));

        expect(scan.bars[0].tone).toBe('weak');
        expect(scan.bars[0].heightPercent).toBe(8);
    });

    it('reports the most recent and the most confident frame by their place in the clip', () => {
        const scan = frameScan(progress({
            currentFrame: 3,
            frameResults: [
                { label: 'Great Tit', score: 0.55 },
                { label: 'Blue Tit', score: 0.88 },
                { label: 'Blue Tit', score: 0.7 }
            ]
        }));

        expect(scan.latest).toEqual({ position: 3, label: 'Blue Tit', scorePercent: 70, thumb: null });
        expect(scan.best).toEqual({ position: 2, label: 'Blue Tit', scorePercent: 88, thumb: null });
    });

    it('leaves a frame that sent no result as waiting even when later frames have arrived', () => {
        const results: Parameters<typeof frameScan>[0]['frameResults'] = [];
        results[2] = { label: 'Blue Tit', score: 0.8 };
        const scan = frameScan(progress({ currentFrame: 3, frameResults: results }));

        expect(scan.bars.map((bar) => bar.tone)).toEqual(['pending', 'pending', 'strong', 'pending']);
        expect(scan.readCount).toBe(1);
    });

    it('has no next frame once the run is complete', () => {
        const scan = frameScan(progress({ currentFrame: 4, status: 'completed' }));

        expect(scan.complete).toBe(true);
        expect(scan.nextPosition).toBeNull();
    });

    it('treats a missing or invalid frame count as a single waiting frame', () => {
        const scan = frameScan(progress({ totalFrames: Number.NaN, currentFrame: Number.NaN }));

        expect(scan.bars).toHaveLength(1);
        expect(scan.nextPosition).toBe(1);
    });

    it('ignores a non-finite score instead of drawing a bar for it', () => {
        const scan = frameScan(progress({ currentFrame: 1, frameResults: [{ label: 'Blue Tit', score: Number.NaN }] }));

        expect(scan.bars[0].tone).toBe('pending');
        expect(scan.latest).toBeNull();
    });
});
