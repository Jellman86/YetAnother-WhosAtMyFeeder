import { describe, expect, it } from 'vitest';
import { namesCameras } from './field-log';

describe('namesCameras', () => {
    it('leaves the camera off rows when every visit in the log came from one camera', () => {
        expect(namesCameras([{ camera: 'birdcam' }, { camera: 'birdcam' }])).toBe(false);
    });

    it('names the camera on every row once the log holds two cameras', () => {
        expect(namesCameras([{ camera: 'birdcam' }, { camera: 'nestcam' }])).toBe(true);
    });

    it('says nothing about cameras for an empty log', () => {
        expect(namesCameras([])).toBe(false);
    });
});
