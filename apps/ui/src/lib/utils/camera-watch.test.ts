import { describe, expect, it } from 'vitest';
import {
    applyCameraWatchMode,
    cameraWatchRows,
    formatCameraList,
    gardenMotionWithinGarden,
    setCameraRole,
    setGardenMotion,
    watchEveryCameraForBirds,
    type CameraWatchContext,
    type CameraWatchSettings
} from './camera-watch';

const FRIGATE = ['patio', 'front', 'greenhouse'];

function settings(overrides: Partial<CameraWatchSettings> = {}): CameraWatchSettings {
    return { cameras: ['patio', 'front'], gardenCameras: [], gardenMotionCameras: [], cameraRoles: {}, ...overrides };
}

function context(overrides: Partial<CameraWatchContext> = {}): CameraWatchContext {
    return { frigateCameras: FRIGATE, gardenEnabled: true, ...overrides };
}

function modes(value: CameraWatchSettings, ctx: CameraWatchContext = context()): Record<string, string> {
    return Object.fromEntries(cameraWatchRows(value, ctx).map(row => [row.camera, row.mode]));
}

function applied(value: CameraWatchSettings, camera: string, mode: Parameters<typeof applyCameraWatchMode>[2], ctx: CameraWatchContext = context()): CameraWatchSettings {
    const change = applyCameraWatchMode(value, camera, mode, ctx);
    if (!change.ok) throw new Error(`Expected ${camera} to switch to ${mode}, blocked by ${change.reason}`);
    return change.settings;
}

describe('deriving what each camera watches for', () => {
    it('combines the bird list and the Garden list into one mode per Frigate camera', () => {
        expect(modes(settings({ cameras: ['patio', 'front'], gardenCameras: ['patio', 'greenhouse'] }))).toEqual({
            patio: 'both',
            front: 'birds',
            greenhouse: 'garden'
        });
    });

    it('reads an empty bird list as every Frigate camera watching for birds', () => {
        expect(modes(settings({ cameras: [], gardenCameras: ['greenhouse'] }))).toEqual({
            patio: 'birds',
            front: 'birds',
            greenhouse: 'both'
        });
    });

    it('offers only birds or off while the Garden beta is off, keeping its saved Garden cameras out of view', () => {
        expect(modes(settings({ gardenCameras: ['patio', 'greenhouse'] }), context({ gardenEnabled: false }))).toEqual({
            patio: 'birds',
            front: 'birds',
            greenhouse: 'off'
        });
    });

    it('keeps configured cameras that Frigate no longer lists, marked as missing rather than dropped', () => {
        const rows = cameraWatchRows(settings({ cameras: ['patio', 'shed'], gardenCameras: ['pond'] }), context());
        expect(rows.map(row => [row.camera, row.mode, row.presence])).toEqual([
            ['patio', 'birds', 'found'],
            ['front', 'off', 'found'],
            ['greenhouse', 'off', 'found'],
            ['shed', 'birds', 'missing'],
            ['pond', 'garden', 'missing']
        ]);
    });

    it('does not list a missing Garden-only camera while the Garden beta is off', () => {
        const rows = cameraWatchRows(settings({ cameras: ['patio'], gardenCameras: ['pond'] }), context({ gardenEnabled: false }));
        expect(rows.map(row => row.camera)).toEqual(['patio', 'front', 'greenhouse']);
    });

    it('says presence is unchecked, not missing, when the Frigate camera list has not been read', () => {
        const rows = cameraWatchRows(settings({ cameras: ['patio'], gardenCameras: ['pond'] }), context({ frigateCameras: null }));
        expect(rows.map(row => [row.camera, row.mode, row.presence])).toEqual([
            ['patio', 'birds', 'unchecked'],
            ['pond', 'garden', 'unchecked']
        ]);
    });

    it('reports the bird role only for cameras watching for birds, and motion only for Garden cameras', () => {
        const rows = cameraWatchRows(settings({
            cameras: ['patio'],
            gardenCameras: ['greenhouse'],
            gardenMotionCameras: ['greenhouse', 'front'],
            cameraRoles: { patio: 'nest', front: 'nest' }
        }), context());
        expect(rows.map(row => [row.camera, row.role, row.collectsMotion])).toEqual([
            ['patio', 'nest', false],
            ['front', null, false],
            ['greenhouse', null, true]
        ]);
    });
});

describe('changing what a camera watches for', () => {
    it('sets a camera to Garden animals only, then Both, then Off', () => {
        const start = settings({ cameras: ['patio', 'front'] });
        const gardenOnly = applied(start, 'patio', 'garden');
        expect(gardenOnly).toEqual(settings({ cameras: ['front'], gardenCameras: ['patio'] }));

        const both = applied(gardenOnly, 'patio', 'both');
        expect(both).toEqual(settings({ cameras: ['front', 'patio'], gardenCameras: ['patio'] }));

        const off = applied(both, 'patio', 'off');
        expect(off).toEqual(settings({ cameras: ['front'], gardenCameras: [] }));
    });

    it('lists every other Frigate camera before removing one from an empty, watch-everything bird list', () => {
        const next = applied(settings({ cameras: [] }), 'front', 'garden');
        expect(next.cameras).toEqual(['patio', 'greenhouse']);
        expect(next.gardenCameras).toEqual(['front']);
        expect(modes(next)).toEqual({ patio: 'birds', front: 'garden', greenhouse: 'birds' });
    });

    it('leaves an empty bird list alone when a camera keeps watching for birds', () => {
        const next = applied(settings({ cameras: [] }), 'front', 'both');
        expect(next.cameras).toEqual([]);
        expect(next.gardenCameras).toEqual(['front']);
    });

    it('never removes the last bird camera, because an empty list would watch every camera', () => {
        const only = settings({ cameras: ['patio'], gardenCameras: ['front'] });
        expect(applyCameraWatchMode(only, 'patio', 'off', context())).toEqual({ ok: false, reason: 'last_bird_camera' });
        expect(applyCameraWatchMode(only, 'patio', 'garden', context())).toEqual({ ok: false, reason: 'last_bird_camera' });
        expect(applied(only, 'patio', 'both').cameras).toEqual(['patio']);
    });

    it('never removes the only Frigate camera from an empty bird list', () => {
        const ctx = context({ frigateCameras: ['patio'] });
        expect(applyCameraWatchMode(settings({ cameras: [] }), 'patio', 'garden', ctx)).toEqual({ ok: false, reason: 'last_bird_camera' });
    });

    it('cannot list the other cameras for an empty bird list until the Frigate camera list is read', () => {
        const ctx = context({ frigateCameras: null });
        expect(applyCameraWatchMode(settings({ cameras: [], gardenCameras: ['pond'] }), 'pond', 'garden', ctx))
            .toEqual({ ok: false, reason: 'camera_list_unread' });
    });

    it('states each blocked choice and its reason on the row', () => {
        const rows = cameraWatchRows(settings({ cameras: ['patio'] }), context());
        expect(rows.find(row => row.camera === 'patio')?.blocked).toEqual({ off: 'last_bird_camera', garden: 'last_bird_camera' });
        expect(rows.find(row => row.camera === 'front')?.blocked).toEqual({});
    });

    it('blocks turning birds off for the last bird camera while the Garden beta is off', () => {
        const ctx = context({ gardenEnabled: false });
        const rows = cameraWatchRows(settings({ cameras: ['patio'] }), ctx);
        expect(rows.find(row => row.camera === 'patio')?.blocked).toEqual({ off: 'last_bird_camera' });
        expect(applyCameraWatchMode(settings({ cameras: ['patio'] }), 'patio', 'off', ctx)).toEqual({ ok: false, reason: 'last_bird_camera' });
    });

    it('refuses a Garden choice while the Garden beta is off and leaves the saved Garden cameras untouched', () => {
        const ctx = context({ gardenEnabled: false });
        const start = settings({ gardenCameras: ['patio'], gardenMotionCameras: ['patio'] });
        expect(applyCameraWatchMode(start, 'front', 'garden', ctx)).toEqual({ ok: false, reason: 'garden_off' });
        const off = applied(start, 'patio', 'off', ctx);
        expect(off).toEqual(settings({ cameras: ['front'], gardenCameras: ['patio'], gardenMotionCameras: ['patio'] }));
    });

    it('stops collecting motion photos when a camera stops watching for Garden animals', () => {
        const start = settings({ gardenCameras: ['patio', 'greenhouse'], gardenMotionCameras: ['patio', 'greenhouse'] });
        expect(applied(start, 'patio', 'birds')).toEqual(settings({ gardenCameras: ['greenhouse'], gardenMotionCameras: ['greenhouse'] }));
    });

    it('drops the bird role of a camera that stops watching for birds, so a nest window is not kept for it', () => {
        const start = settings({ cameras: ['patio', 'front'], cameraRoles: { patio: 'nest', front: 'nest' } });
        expect(applied(start, 'patio', 'garden').cameraRoles).toEqual({ front: 'nest' });
        expect(applied(start, 'patio', 'both').cameraRoles).toEqual({ patio: 'nest', front: 'nest' });
    });

    it('lets a missing camera be turned off so a stale entry can be cleared', () => {
        const next = applied(settings({ cameras: ['patio', 'shed'], gardenCameras: ['shed'] }), 'shed', 'off');
        expect(next).toEqual(settings({ cameras: ['patio'], gardenCameras: [] }));
        expect(cameraWatchRows(next, context()).map(row => row.camera)).toEqual(FRIGATE);
    });

    it('does not mutate the settings it was given', () => {
        const start = settings({ cameras: ['patio', 'front'], gardenCameras: ['patio'], gardenMotionCameras: ['patio'], cameraRoles: { patio: 'nest' } });
        const frozen = JSON.stringify(start);
        applied(start, 'patio', 'off');
        expect(JSON.stringify(start)).toBe(frozen);
    });
});

describe('watching every camera for birds', () => {
    it('writes the empty bird list that means every camera, keeping Garden choices and roles', () => {
        const start = settings({ cameras: ['patio'], gardenCameras: ['front'], gardenMotionCameras: ['front'], cameraRoles: { patio: 'nest' } });
        expect(watchEveryCameraForBirds(start)).toEqual({ ...start, cameras: [] });
    });
});

describe('bird roles and motion photos', () => {
    it('stores Nest and forgets Feeder, the default the server does not keep', () => {
        const nest = setCameraRole(settings(), 'patio', 'nest');
        expect(nest.cameraRoles).toEqual({ patio: 'nest' });
        expect(setCameraRole(nest, 'patio', 'feeder').cameraRoles).toEqual({});
    });

    it('collects motion photos only on a Garden camera', () => {
        const start = settings({ gardenCameras: ['patio'] });
        expect(setGardenMotion(start, 'patio', true).gardenMotionCameras).toEqual(['patio']);
        expect(setGardenMotion(start, 'front', true).gardenMotionCameras).toEqual([]);
        expect(setGardenMotion(settings({ gardenCameras: ['patio'], gardenMotionCameras: ['patio'] }), 'patio', false).gardenMotionCameras).toEqual([]);
    });

    it('ignores saved motion cameras that are no longer Garden cameras', () => {
        expect(gardenMotionWithinGarden(['patio'], ['patio', 'front'])).toEqual(['patio']);
    });
});

describe('naming cameras in a sentence', () => {
    it('joins camera names in the reader’s language', () => {
        expect(formatCameraList(['patio', 'greenhouse'], 'en')).toBe('patio and greenhouse');
        expect(formatCameraList(['patio', 'front', 'greenhouse'], 'en')).toBe('patio, front, and greenhouse');
        expect(formatCameraList(['patio', 'greenhouse'], 'de')).toBe('patio und greenhouse');
    });

    it('falls back to commas when the locale is unknown to the browser', () => {
        expect(formatCameraList(['patio', 'front'], 'not a locale')).toBe('patio, front');
    });
});
