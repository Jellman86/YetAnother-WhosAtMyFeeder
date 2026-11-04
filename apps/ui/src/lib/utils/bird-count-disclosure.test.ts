import { describe, expect, it } from 'vitest';
import type { BirdScanResponse } from '../api/media';
import { birdCountDisclosure, countRegionImageStyle, countRegionOutlineStyle } from './bird-count-disclosure';

const completed: BirdScanResponse = {
    event_id: 'event', candidate_id: 'scene', status: 'completed', available: true, result_count: 2
};
const region = { candidate_id: 'uncertain', box: [10, 10, 30, 30] as [number, number, number, number], detector_confidence: 0.4, reason: 'individuality_unresolved' };

describe('count disclosure', () => {
    it('never labels an older scan as confirmed', () => {
        expect(birdCountDisclosure(completed)?.kind).toBe('legacy');
    });
    it('states incompleteness even when the confirmed lower bound is zero', () => {
        expect(birdCountDisclosure({ ...completed, result_count: 0, count_status: 'incomplete', unconfirmed_regions: [region] }))
            .toEqual({ kind: 'incomplete', count: 0, unconfirmed: 1, excluded: 0 });
    });
    it('does not treat excluded nonbirds as unconfirmed or counted birds', () => {
        expect(birdCountDisclosure({ ...completed, count_status: 'complete', excluded_regions: [region] }))
            .toEqual({ kind: 'complete', count: 2, unconfirmed: 0, excluded: 1 });
    });
    it('does not round an unavailable count down to zero', () => {
        expect(birdCountDisclosure({ ...completed, result_count: null })?.kind).toBe('unavailable');
        expect(birdCountDisclosure({ ...completed, status: 'running' })).toBeNull();
    });
    it('never claims completeness while unconfirmed regions are present', () => {
        expect(birdCountDisclosure({ ...completed, count_status: 'complete', unconfirmed_regions: [region] })?.kind).toBe('incomplete');
    });
});

describe('uncounted region images', () => {
    it('uses only geometry measured from the loaded full-resolution image', () => {
        expect(countRegionImageStyle([10, 10, 30, 30], { width: 100, height: 80 })).toContain('max-width:none');
        expect(countRegionImageStyle([10, 10, 110, 30], { width: 100, height: 80 })).toBeUndefined();
        expect(countRegionImageStyle([10, 10, 30, 30], null)).toBeUndefined();
    });
    it('outlines exactly the flagged box inside the square crop', () => {
        // A 20 x 10 box in a crop 1.3 times its longer side: the box fills 1/1.3 by 1/2.6.
        const style = countRegionOutlineStyle([10, 10, 30, 20]);
        expect(style).toBe('left:11.538%;top:30.769%;width:76.923%;height:38.462%');
        expect(countRegionOutlineStyle([30, 10, 10, 20])).toBeUndefined();
    });
});
