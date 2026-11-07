export interface CameraChoice {
    camera: string;
    /** Saved but not in Frigate: it will never produce a detection. */
    missing: boolean;
}

/** Frigate's cameras, then any saved names it does not have, so a stale one can be seen and unticked. */
export function cameraChoices(frigateCameras: readonly string[], saved: readonly string[]): CameraChoice[] {
    const known = new Set(frigateCameras);
    return [
        ...frigateCameras.map((camera) => ({ camera, missing: false })),
        ...saved.filter((camera) => !known.has(camera)).map((camera) => ({ camera, missing: true }))
    ];
}

/** The camera names in Frigate's config, or null when the reply does not have any to offer. */
export function frigateCameraNames(config: unknown): string[] | null {
    if (!config || typeof config !== 'object' || !('cameras' in config)) return null;
    const cameras = config.cameras;
    if (!cameras || typeof cameras !== 'object') return null;
    const names = Object.keys(cameras);
    return names.length > 0 ? names : null;
}

export function parseCameraNames(text: string): string[] {
    return [...new Set(text.split(',').map((name) => name.trim()).filter(Boolean))];
}
