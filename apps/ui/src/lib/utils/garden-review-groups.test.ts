import { describe, expect, it } from 'vitest';
import type { GardenCapture } from '../api/garden';
import { groupGardenReview } from './garden-review-groups';

function capture(id: string, box: [number, number, number, number] = [0.78, 0.60, 0.03, 0.09]): GardenCapture {
    return { id, camera: 'patio', frigate_label: 'animal', observed_at: '2026-10-14T01:00:00Z', status: 'pending', reviewed_at: null,
        snapshot_url: `/api/garden/${id}/snapshot`, source_kind: 'motion', motion_source: {
            camera: 'patio', clip_start: 1, clip_end: 9, frame_index: 1, frame_offset: 1,
            clip_sha256: 'a'.repeat(64), image_sha256: 'b'.repeat(64), detector_sha256: 'c'.repeat(64),
            detector_score: 0.6, box_xywh: box
        } };
}

describe('Garden review groups describe position, never animal identity', () => {
    it('groups repeated feeder proposals when the detector changes the box extent', () => {
        const items = [
            capture('anchor', [0.7787210464, 0.6029235840, 0.0294397354, 0.0996236165]),
            capture('wider', [0.7807638645, 0.6024082184, 0.0539882183, 0.0722991943]),
            capture('taller', [0.7797590256, 0.6019916534, 0.0315879822, 0.1271631241]),
            capture('shorter', [0.7814696312, 0.6021912893, 0.0293195724, 0.0882186254])
        ];
        expect(groupGardenReview(items).map(group => group.items.map(item => item.id)))
            .toEqual([['anchor', 'wider', 'taller', 'shorter']]);
    });
    it('does not merge a much larger proposal merely because it contains another', () => {
        expect(groupGardenReview([capture('small', [0.1, 0.2, 0.03, 0.09]),
            capture('large', [0.1, 0.2, 0.2, 0.3])])).toHaveLength(2);
    });
    it('reduces 109 feeder proposals to one group while retaining every exact capture', () => {
        const items = Array.from({ length: 109 }, (_, index) => capture(String(index)));
        const groups = groupGardenReview(items);
        expect(groups).toHaveLength(1);
        expect(groups[0].items).toEqual(items);
        expect(items).toHaveLength(109);
    });
    it('keeps another area, camera, model or source separate', () => {
        const item = capture('one');
        const items = [item, capture('jitter', [0.781, 0.601, 0.03, 0.09]), capture('elsewhere', [0.8, 0.54, 0.05, 0.04]),
            { ...capture('camera'), camera: 'other' }, { ...capture('frigate'), source_kind: 'frigate_event' as const },
            { ...capture('model'), motion_source: { ...capture('model').motion_source as NonNullable<GardenCapture['motion_source']>, detector_sha256: 'd'.repeat(64) } }];
        expect(groupGardenReview(items).map(group => group.items.map(row => row.id))).toEqual([['one', 'jitter'], ['elsewhere'], ['camera'], ['frigate'], ['model']]);
    });
    it('does not chain a moving animal across the image or group confirmed history', () => {
        const items = [capture('a', [0.10, 0.2, 0.1, 0.1]), capture('b', [0.11, 0.2, 0.1, 0.1]), capture('c', [0.12, 0.2, 0.1, 0.1]),
            { ...capture('confirmed'), status: 'confirmed' as const }, { ...capture('dismissed'), status: 'dismissed' as const }];
        expect(groupGardenReview(items).map(group => group.items.length)).toEqual([2, 1, 1, 1]);
    });
    it('fails open to individual cards for missing or invalid geometry', () => {
        const item = capture('a');
        expect(groupGardenReview([{ ...item, motion_source: null }, capture('b', [NaN, 0, 0.1, 0.1]), capture('c', [0.95, 0, 0.1, 0.1])])).toHaveLength(3);
    });
});
