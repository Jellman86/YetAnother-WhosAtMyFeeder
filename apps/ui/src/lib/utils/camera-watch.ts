/**
 * What each Frigate camera is watched for, derived from the independent lists the server keeps.
 *
 * The server stores birds and Garden animals separately: `cameras` lists the bird cameras, and an
 * empty list means every Frigate camera; `garden_cameras` lists the Garden cameras, and
 * `garden_motion_cameras` the Garden cameras that also collect motion photos. Settings shows one
 * choice per camera instead, so every change here has to land back in those lists without
 * changing what the server already means by them.
 */

export type CameraWatchMode = 'off' | 'birds' | 'garden' | 'both';
export type CameraRole = 'feeder' | 'nest';

/** Why a camera cannot switch to a mode. Each reason is worded for the owner by the view. */
export type CameraWatchBlock = 'last_bird_camera' | 'camera_list_unread' | 'garden_off';

/** Whether Frigate lists a camera, or whether that is unknown because the list was not read. */
type CameraPresence = 'found' | 'missing' | 'unchecked';

export interface CameraWatchSettings {
    /** Bird cameras. An empty list means every Frigate camera. */
    cameras: readonly string[];
    gardenCameras: readonly string[];
    /** A subset of `gardenCameras`. */
    gardenMotionCameras: readonly string[];
    /** Only Nest is stored; a camera without an entry is a feeder. */
    cameraRoles: Readonly<Record<string, CameraRole>>;
}

export interface CameraWatchContext {
    /** Cameras Frigate reports, or null when the list has not been read. */
    frigateCameras: readonly string[] | null;
    /** The Garden animals beta; while it is off, a camera watches for birds or nothing. */
    gardenEnabled: boolean;
}

export interface CameraWatchRow {
    camera: string;
    mode: CameraWatchMode;
    presence: CameraPresence;
    /** The bird role, or null when the camera does not watch for birds. */
    role: CameraRole | null;
    collectsMotion: boolean;
    /** Modes this camera cannot switch to, with the reason for each. */
    blocked: Partial<Record<CameraWatchMode, CameraWatchBlock>>;
}

export type CameraWatchChange =
    | { ok: true; settings: CameraWatchSettings }
    | { ok: false; reason: CameraWatchBlock };

const ALL_MODES: readonly CameraWatchMode[] = ['off', 'birds', 'garden', 'both'];

export function watchesEveryCameraForBirds(settings: CameraWatchSettings): boolean {
    return settings.cameras.length === 0;
}

function watchesForBirds(camera: string, settings: CameraWatchSettings): boolean {
    return watchesEveryCameraForBirds(settings) || settings.cameras.includes(camera);
}

function includesBirds(mode: CameraWatchMode): boolean {
    return mode === 'birds' || mode === 'both';
}

function includesGarden(mode: CameraWatchMode): boolean {
    return mode === 'garden' || mode === 'both';
}

function modeOf(birds: boolean, garden: boolean): CameraWatchMode {
    if (birds && garden) return 'both';
    if (birds) return 'birds';
    return garden ? 'garden' : 'off';
}

function cameraMode(camera: string, settings: CameraWatchSettings, ctx: CameraWatchContext): CameraWatchMode {
    const garden = ctx.gardenEnabled && settings.gardenCameras.includes(camera);
    return modeOf(watchesForBirds(camera, settings), garden);
}

/** The bird list once `camera` stops watching for birds, or the reason it cannot. */
function birdCamerasWithout(
    camera: string,
    settings: CameraWatchSettings,
    ctx: CameraWatchContext
): { ok: true; cameras: string[] } | { ok: false; reason: CameraWatchBlock } {
    // An empty list means every camera, so removing one first has to name all the others;
    // otherwise they would silently stop watching for birds.
    let source: readonly string[] = settings.cameras;
    if (watchesEveryCameraForBirds(settings)) {
        if (ctx.frigateCameras === null) return { ok: false, reason: 'camera_list_unread' };
        source = ctx.frigateCameras;
    }
    const remaining = source.filter(name => name !== camera);
    // An emptied list would quietly mean every camera again, the opposite of what was asked.
    if (remaining.length === 0) return { ok: false, reason: 'last_bird_camera' };
    return { ok: true, cameras: remaining };
}

function blockFor(
    camera: string,
    target: CameraWatchMode,
    settings: CameraWatchSettings,
    ctx: CameraWatchContext
): CameraWatchBlock | null {
    if (includesGarden(target) && !ctx.gardenEnabled) return 'garden_off';
    if (includesBirds(target) || !watchesForBirds(camera, settings)) return null;
    const without = birdCamerasWithout(camera, settings, ctx);
    return without.ok ? null : without.reason;
}

export function cameraWatchRows(settings: CameraWatchSettings, ctx: CameraWatchContext): CameraWatchRow[] {
    const configured = [...settings.cameras, ...(ctx.gardenEnabled ? settings.gardenCameras : [])];
    const names = [...new Set([...(ctx.frigateCameras ?? []), ...configured])];
    const offered = ctx.gardenEnabled ? ALL_MODES : ALL_MODES.filter(mode => !includesGarden(mode));
    return names.map(camera => {
        const mode = cameraMode(camera, settings, ctx);
        const blocked: Partial<Record<CameraWatchMode, CameraWatchBlock>> = {};
        for (const target of offered) {
            if (target === mode) continue;
            const reason = blockFor(camera, target, settings, ctx);
            if (reason) blocked[target] = reason;
        }
        return {
            camera,
            mode,
            presence: ctx.frigateCameras === null ? 'unchecked' : ctx.frigateCameras.includes(camera) ? 'found' : 'missing',
            role: includesBirds(mode) ? settings.cameraRoles[camera] ?? 'feeder' : null,
            collectsMotion: includesGarden(mode) && settings.gardenMotionCameras.includes(camera),
            blocked
        };
    });
}

export function applyCameraWatchMode(
    settings: CameraWatchSettings,
    camera: string,
    mode: CameraWatchMode,
    ctx: CameraWatchContext
): CameraWatchChange {
    const reason = blockFor(camera, mode, settings, ctx);
    if (reason) return { ok: false, reason };

    let cameras = [...settings.cameras];
    let cameraRoles = { ...settings.cameraRoles };
    if (includesBirds(mode)) {
        if (!watchesForBirds(camera, settings)) cameras.push(camera);
    } else if (watchesForBirds(camera, settings)) {
        const without = birdCamerasWithout(camera, settings, ctx);
        if (!without.ok) return without;
        cameras = without.cameras;
    }
    // A camera that no longer watches for birds has no bird role; keeping a Nest entry would
    // keep the nest window on screen for a camera that cannot use it.
    if (!includesBirds(mode)) delete cameraRoles[camera];

    let gardenCameras = [...settings.gardenCameras];
    let gardenMotionCameras = [...settings.gardenMotionCameras];
    // While the beta is off its saved cameras stay as they are, for when it is turned on again.
    if (ctx.gardenEnabled) {
        if (includesGarden(mode)) {
            if (!gardenCameras.includes(camera)) gardenCameras.push(camera);
        } else {
            gardenCameras = gardenCameras.filter(name => name !== camera);
            gardenMotionCameras = gardenMotionCameras.filter(name => name !== camera);
        }
    }
    return { ok: true, settings: { cameras, gardenCameras, gardenMotionCameras, cameraRoles } };
}

/** The empty bird list: every Frigate camera, including cameras added to Frigate later. */
export function watchEveryCameraForBirds(settings: CameraWatchSettings): CameraWatchSettings {
    return { ...settings, cameras: [] };
}

export function setCameraRole(settings: CameraWatchSettings, camera: string, role: CameraRole): CameraWatchSettings {
    const cameraRoles = { ...settings.cameraRoles };
    // The server keeps only Nest; Feeder is what a camera without an entry already is.
    if (role === 'nest') cameraRoles[camera] = 'nest';
    else delete cameraRoles[camera];
    return { ...settings, cameraRoles };
}

export function setGardenMotion(settings: CameraWatchSettings, camera: string, collect: boolean): CameraWatchSettings {
    const others = settings.gardenMotionCameras.filter(name => name !== camera);
    const allowed = collect && settings.gardenCameras.includes(camera);
    return { ...settings, gardenMotionCameras: allowed ? [...others, camera] : others };
}

/** Saved motion cameras that are still Garden cameras; the others collect nothing. */
export function gardenMotionWithinGarden(gardenCameras: readonly string[], motionCameras: readonly string[]): string[] {
    return motionCameras.filter(name => gardenCameras.includes(name));
}

export function formatCameraList(cameras: readonly string[], locale: string): string {
    try {
        return new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' }).format(cameras);
    } catch {
        return cameras.join(', ');
    }
}
