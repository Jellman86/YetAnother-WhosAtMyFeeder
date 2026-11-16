import { frigateCameraNames } from './camera-choices';

/** How long the wizard waits for Frigate's camera list before offering typed names instead. */
export const FRIGATE_CAMERA_READ_LIMIT_MS = 8000;

export type CameraListRead =
    | { state: 'reading' }
    | { state: 'read'; cameras: string[] }
    /** `timed_out`: no answer within the limit. `failed`: Frigate answered with an error or listed no cameras. */
    | { state: 'unavailable'; cause: 'timed_out' | 'failed' };

/**
 * Reads Frigate's cameras with a bounded wait.
 *
 * A Frigate that is down can hold the request for a minute. The step must not sit behind that, so
 * the request is aborted at the limit and the outcome says it timed out.
 */
export async function readCameraList(
    fetchConfig: (signal: AbortSignal) => Promise<unknown>,
    limitMs: number = FRIGATE_CAMERA_READ_LIMIT_MS
): Promise<Exclude<CameraListRead, { state: 'reading' }>> {
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
    }, limitMs);
    try {
        const cameras = frigateCameraNames(await fetchConfig(controller.signal));
        return cameras ? { state: 'read', cameras } : { state: 'unavailable', cause: 'failed' };
    } catch {
        return { state: 'unavailable', cause: timedOut ? 'timed_out' : 'failed' };
    } finally {
        clearTimeout(timer);
    }
}
