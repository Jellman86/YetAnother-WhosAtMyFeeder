import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FRIGATE_CAMERA_READ_LIMIT_MS, readCameraList } from './camera-list-read';

describe("reading Frigate's cameras for the wizard", () => {
    beforeEach(() => { vi.useFakeTimers(); });
    afterEach(() => { vi.useRealTimers(); });

    it('returns the cameras Frigate lists', async () => {
        await expect(readCameraList(async () => ({ cameras: { feeder: {}, nestbox: {} } }))).resolves.toEqual({
            state: 'read', cameras: ['feeder', 'nestbox']
        });
    });

    it('says Frigate could not be read when the request fails or lists nothing', async () => {
        await expect(readCameraList(async () => { throw new Error('502'); })).resolves.toEqual({ state: 'unavailable', cause: 'failed' });
        await expect(readCameraList(async () => ({ cameras: {} }))).resolves.toEqual({ state: 'unavailable', cause: 'failed' });
    });

    it('gives up after the stated limit instead of waiting for Frigate to time out', async () => {
        let aborted = false;
        const read = readCameraList((signal) => new Promise((_, reject) => {
            signal.addEventListener('abort', () => { aborted = true; reject(new DOMException('aborted', 'AbortError')); });
        }));
        await vi.advanceTimersByTimeAsync(FRIGATE_CAMERA_READ_LIMIT_MS - 1);
        expect(aborted).toBe(false);
        await vi.advanceTimersByTimeAsync(1);
        await expect(read).resolves.toEqual({ state: 'unavailable', cause: 'timed_out' });
        expect(aborted).toBe(true);
    });

    it('keeps the wait short enough to say in a sentence', () => {
        expect(FRIGATE_CAMERA_READ_LIMIT_MS).toBe(8000);
    });
});
