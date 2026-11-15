import { describe, expect, it } from 'vitest';
import { videoHeadingFor } from './video-heading';

describe('videoHeadingFor', () => {
    it('titles a clip by the bird, in the naming style the owner chose, and its time', () => {
        const detection = { display_name: 'Parus major', common_name: 'Great Tit', scientific_name: 'Parus major', detection_time: '2026-11-14T18:20:00Z' };
        expect(videoHeadingFor(detection, true, false)).toEqual({ name: 'Great Tit', at: '2026-11-14T18:20:00Z' });
        expect(videoHeadingFor(detection, true, true).name).toBe('Parus major');
    });

    it('leaves the time out when the record has none', () => {
        expect(videoHeadingFor({ display_name: 'Dunnock' }, true, false)).toEqual({ name: 'Dunnock', at: null });
    });
});
