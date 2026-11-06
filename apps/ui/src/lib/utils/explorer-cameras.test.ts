import { describe, expect, it } from 'vitest';
import { explorerCameraOptions, seenGardenCameras } from './explorer-cameras';

const birdCameras = ['birdcam', 'patio'];
const birdCounts = { birdcam: 12, patio: 3 };

describe('explorerCameraOptions', () => {
    it('lists the bird cameras with their bird counts under Birds', () => {
        expect(explorerCameraOptions({ subjects: 'birds', birdCameras, birdCounts, gardenCameras: ['greenhousecam'], chosen: '' })).toEqual({
            cameras: ['birdcam', 'patio'],
            counts: birdCounts
        });
    });

    it('lists the Garden cameras without counts under Garden animals, including a Garden-only camera', () => {
        // A bird count beside a Garden camera would claim animals that were never counted.
        expect(explorerCameraOptions({ subjects: 'garden', birdCameras, birdCounts, gardenCameras: ['patio', 'greenhousecam'], chosen: '' })).toEqual({
            cameras: ['greenhousecam', 'patio'],
            counts: null
        });
    });

    it('lists every camera once without counts under Both', () => {
        expect(explorerCameraOptions({ subjects: 'all', birdCameras, birdCounts, gardenCameras: ['patio', 'greenhousecam'], chosen: '' })).toEqual({
            cameras: ['birdcam', 'greenhousecam', 'patio'],
            counts: null
        });
    });

    it('keeps a chosen camera in the list so it can be seen and removed, even when nothing names it', () => {
        expect(explorerCameraOptions({ subjects: 'garden', birdCameras, birdCounts, gardenCameras: [], chosen: 'shedcam' }).cameras).toEqual(['shedcam']);
        expect(explorerCameraOptions({ subjects: 'birds', birdCameras, birdCounts, gardenCameras: [], chosen: 'birdcam' }).cameras).toEqual(['birdcam', 'patio']);
    });
});

describe('seenGardenCameras', () => {
    it('gathers the cameras of the Garden captures read so far, never losing one to a narrower page', () => {
        const first = seenGardenCameras([], [{ camera: 'patio' }, { camera: 'greenhousecam' }, { camera: 'patio' }]);
        expect(first).toEqual(['greenhousecam', 'patio']);
        expect(seenGardenCameras(first, [{ camera: 'patio' }])).toBe(first);
    });

    it('never offers the placeholder a visitor sees when camera names are not shared', () => {
        expect(seenGardenCameras([], [{ camera: 'Hidden' }])).toEqual([]);
    });
});
