import { describe, expect, it } from 'vitest';
import { viewerCameraNames } from './camera-viewer';

describe('viewerCameraNames', () => {
    it('lists bird cameras when Garden animals is off', () => {
        expect(viewerCameraNames({ cameras: ['birdcam', 'patiocam'], garden_cameras: ['greenhousecam'], beta_garden_animals: false }))
            .toEqual(['birdcam', 'patiocam']);
    });

    it('adds Garden-only cameras after the bird cameras when Garden animals is on', () => {
        expect(viewerCameraNames({ cameras: ['birdcam', 'patiocam'], garden_cameras: ['patiocam', 'greenhousecam'], beta_garden_animals: true }))
            .toEqual(['birdcam', 'patiocam', 'greenhousecam']);
    });

    it('keeps an empty bird list meaning every Frigate camera', () => {
        expect(viewerCameraNames({ cameras: [], garden_cameras: ['greenhousecam'], beta_garden_animals: true })).toEqual([]);
    });

    it('drops blank and duplicate names', () => {
        expect(viewerCameraNames({ cameras: ['birdcam', ' ', 'birdcam'], garden_cameras: ['', 'greenhousecam'], beta_garden_animals: true }))
            .toEqual(['birdcam', 'greenhousecam']);
    });
});
