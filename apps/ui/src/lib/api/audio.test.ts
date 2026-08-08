import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock, handleResponseMock } = vi.hoisted(() => ({
    apiFetchMock: vi.fn(),
    handleResponseMock: vi.fn(),
}));

vi.mock('./core', () => ({
    API_BASE: '/api',
    apiFetch: apiFetchMock,
    handleResponse: handleResponseMock,
}));

import { fetchEventAudioContext } from './audio';

describe('fetchEventAudioContext', () => {
    const response = {
        headers: new Headers({ 'X-YAWAMF-Audio-Suppressed-By-Mapping': '2' })
    };
    const detections = [{ species: 'Blue Tit' }];

    beforeEach(() => {
        apiFetchMock.mockReset();
        handleResponseMock.mockReset();
        apiFetchMock.mockResolvedValue(response);
        handleResponseMock.mockResolvedValue(detections);
    });

    it('loads server-scoped context, suppression metadata, and forwards cancellation', async () => {
        const controller = new AbortController();

        await expect(fetchEventAudioContext('event/with spaces', controller.signal)).resolves.toEqual({
            detections,
            suppressed_by_mapping: 2
        });

        expect(apiFetchMock).toHaveBeenCalledWith(
            '/api/audio/context/event/event%2Fwith%20spaces',
            {
                signal: controller.signal,
                timeoutMs: 10_000,
            }
        );
        expect(handleResponseMock).toHaveBeenCalledWith(response);
    });

    it('defaults missing suppression metadata to zero', async () => {
        apiFetchMock.mockResolvedValue({ headers: new Headers() });

        await expect(fetchEventAudioContext('event-1')).resolves.toEqual({
            detections,
            suppressed_by_mapping: 0
        });
    });
});
