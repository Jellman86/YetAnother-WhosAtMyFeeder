import { describe, expect, it } from 'vitest';
import type { GardenCapture } from '../api/garden';
import { gardenPhotoOutline, gardenPreviewStyle } from './garden-photo';

const capture: GardenCapture = {
    id: 'capture', camera: 'patio', frigate_label: 'animal', observed_at: '2026-10-13T18:00:00Z',
    status: 'pending', reviewed_at: null, snapshot_url: '/api/garden/capture/snapshot', source_kind: 'motion',
    motion_source: {
        camera: 'patio', clip_start: 1, clip_end: 9, frame_index: 1, frame_offset: 1,
        clip_sha256: 'a'.repeat(64), image_sha256: 'b'.repeat(64), detector_sha256: 'c'.repeat(64),
        detector_score: 0.8, box_xywh: [0.1, 0.2, 0.3, 0.4]
    }
};

const identification: NonNullable<GardenCapture['identification']> = {
    outcome: 'unknown', review: 'dismissed', variant: '4.0.3b', devices: ['CPU'], country: 'GBR',
    input_kind: 'whole_image', frame_size: [640, 1000], image_sha256: 'b'.repeat(64), model_sha256: 'c'.repeat(64),
    reason: 'unknown', provider: 'cpu', package_sha256: 'd'.repeat(64), output_index: 0, identified_at: '2026-10-13T18:00:00Z'
};

describe('garden photo outlines', () => {
    it('shows the saved detector proposal before presence confirmation or species analysis', () => {
        expect(gardenPhotoOutline(capture, [640, 1000])).toEqual({
            kind: 'presence', box: [0.1, 0.2, 0.3, 0.4], size: [640, 1000]
        });
    });

    it('keeps the presence proposal when a species suggestion is dismissed', () => {
        expect(gardenPhotoOutline({ ...capture, identification }, [640, 1000])?.kind).toBe('presence');
    });

    it('does not invent a box for a Frigate event without recorded geometry', () => {
        expect(gardenPhotoOutline({ ...capture, source_kind: 'frigate_event', motion_source: null }, [640, 1000])).toBeNull();
    });

    it('withholds an outline until the photo is decoded', () => {
        expect(gardenPhotoOutline(capture, undefined)).toBeNull();
        expect(gardenPhotoOutline(capture, [0, 0])).toBeNull();
    });

    it('only draws a species input crop on a photo matching its recorded dimensions', () => {
        const item: GardenCapture = { ...capture, source_kind: 'frigate_event', motion_source: null,
            identification: { ...identification, review: 'unreviewed', input_kind: 'tracked_crop', box_xywh: [0.1, 0.2, 0.3, 0.4] } };
        expect(gardenPhotoOutline(item, [640, 1000])?.kind).toBe('identification');
        expect(gardenPhotoOutline(item, [1280, 720])).toBeNull();
        expect(gardenPhotoOutline({ ...item, identification: { ...identification, box_xywh: [0.1, 0.2, 0.3, 0.4] } }, [640, 1000])).toBeNull();
    });

    const invalidBoxes: [number, number, number, number][] = [[0.9, 0.2, 0.3, 0.4], [-0.1, 0.2, 0.3, 0.4], [0.1, 0.2, 0, 0.4], [0.1, NaN, 0.3, 0.4]];
    for (const box of invalidBoxes) {
        it(`withholds invalid geometry ${String(box)}`, () => {
            const motion_source = capture.motion_source ? { ...capture.motion_source, box_xywh: box } : null;
            expect(gardenPhotoOutline({ ...capture, motion_source }, [640, 1000])).toBeNull();
        });
    }
});


describe('Garden preview crops', () => {
    it('centres the saved animal box, keeps its aspect ratio and fits the whole animal', () => {
        const style = gardenPreviewStyle(capture, [1000, 500], 4 / 3);
        expect(style).not.toBeNull();
        if (!style) throw new Error('Missing saved crop');
        const { width, height, left, top } = style;
        expect(width / height * (4 / 3)).toBeCloseTo(2);
        const x = left + 0.1 * width;
        const y = top + 0.2 * height;
        expect(x).toBeGreaterThanOrEqual(0);
        expect(y).toBeGreaterThanOrEqual(0);
        expect(x + 0.3 * width).toBeLessThanOrEqual(100);
        expect(y + 0.4 * height).toBeLessThanOrEqual(100);
        expect(width).toBeGreaterThan(100);
    });

    it('uses a full photograph when no trustworthy crop is recorded', () => {
        expect(gardenPreviewStyle({ ...capture, motion_source: null }, [1000, 500], 1)).toBeNull();
        expect(gardenPreviewStyle(capture, undefined, 1)).toBeNull();
        expect(gardenPreviewStyle(capture, [1000, 500], 0)).toBeNull();
    });

    it('keeps edge animals inside square row previews without stretching', () => {
        const edge = { ...capture, motion_source: capture.motion_source ? { ...capture.motion_source, box_xywh: [0.8, 0.7, 0.2, 0.3] as [number, number, number, number] } : null };
        const style = gardenPreviewStyle(edge, [1000, 500], 1);
        expect(style).not.toBeNull();
        if (!style) throw new Error('Missing saved crop');
        expect(style.width / style.height).toBeCloseTo(2);
        expect(style.left + style.width).toBeGreaterThanOrEqual(99.99);
        expect(style.top + style.height).toBeGreaterThanOrEqual(99.99);
    });
});


it('never shrinks a near-full-frame animal below a full-photo fit', () => {
    const full = { ...capture, motion_source: capture.motion_source ? { ...capture.motion_source, box_xywh: [0, 0, 1, 1] as [number, number, number, number] } : null };
    const style = gardenPreviewStyle(full, [1000, 500], 4 / 3);
    expect(style?.width).toBeCloseTo(100);
    expect(style?.height).toBeCloseTo(100 * (4 / 3) / 2);
});
