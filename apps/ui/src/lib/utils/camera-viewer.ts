import type { Settings } from '../api/settings';

type ViewerCameraSettings = Pick<Settings, 'cameras' | 'beta_garden_animals'> & {
    garden_cameras?: readonly string[] | null;
};

/**
 * Cameras the header viewer cycles through. An empty result means every Frigate camera, matching
 * an empty bird camera list; otherwise Garden-only cameras follow the bird cameras.
 */
export function viewerCameraNames(settings: ViewerCameraSettings): string[] {
    const birdCameras = settings.cameras.filter((camera) => camera.trim().length > 0);
    if (birdCameras.length === 0) return [];
    const gardenCameras = settings.beta_garden_animals === true ? (settings.garden_cameras ?? []) : [];
    return [...new Set([...birdCameras, ...gardenCameras.filter((camera) => camera.trim().length > 0)])];
}
