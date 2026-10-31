import { describe, expect, it } from 'vitest';
import connectionSource from './ConnectionSettings.svelte?raw';
import settingsSource from '../../pages/Settings.svelte?raw';

describe('the Cameras to watch list', () => {
    const listTag = connectionSource.match(/<div\b[^>]*\bdata-camera-list\b[^>]*>/)?.[0] ?? '';

    it('grows with the page instead of scrolling inside its card', () => {
        // A capped inner scroller slid the first camera under the card header and clipped
        // the nest window beneath the list, which read as a broken panel.
        expect(listTag).not.toBe('');
        expect(listTag).not.toMatch(/overflow-y-auto|max-h-/);
    });

    it('keeps the nest window after the cameras, in the same flow', () => {
        expect(connectionSource.indexOf('data-nest-dedupe')).toBeGreaterThan(connectionSource.indexOf('data-camera-list'));
    });

    it('is one list of camera rows, each choosing birds, Garden animals or both', () => {
        // The owner asked for one selector per camera instead of a bird list here and a second,
        // differently styled Garden list under Beta features.
        expect(connectionSource).toContain('<CameraWatchRow');
        expect(connectionSource).toContain('cameraWatchRows(watchSettings, watchContext)');
        expect(settingsSource).toContain('bind:gardenCameras');
        expect(settingsSource).toContain('bind:gardenMotionCameras');
    });

    it('can be opened from Beta features, landing on the list itself', () => {
        expect(listTag).toContain('id="settings-camera-list"');
        expect(listTag).toContain('tabindex="-1"');
    });

    it('says when every camera watches for birds, and offers that choice back once the list is narrowed', () => {
        expect(connectionSource).toContain('data-bird-scope');
        expect(connectionSource).toContain('watchEveryCameraForBirds(watchSettings)');
        expect(connectionSource).toContain("settings.cameras.every_camera_on");
        expect(connectionSource).toContain("settings.cameras.every_camera_off");
    });

    it('never passes the saved list off as Frigate\'s answer', () => {
        // Settings falls back to the saved cameras when Frigate cannot be read; the rows must
        // then say the list is unread instead of reporting every camera as found.
        expect(connectionSource).toContain('frigateCameras: string[] | null;');
        expect(connectionSource).toContain('data-camera-list-state');
    });
});
