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
    beforeEach(() => {
        apiFetchMock.mockReset();
        handleResponseMock.mockReset();
        apiFetchMock.mockResolvedValue({});
        handleResponseMock.mockReturnValue([]);
    });

    it('loads server-scoped context for the event and forwards cancellation', async () => {
        const controller = new AbortController();

        await expect(fetchEventAudioContext('event/with spaces', controller.signal)).resolves.toEqual([]);

        expect(apiFetchMock).toHaveBeenCalledWith(
            '/api/audio/context/event/event%2Fwith%20spaces',
            {
                signal: controller.signal,
                timeoutMs: 10_000,
            }
        );
        expect(handleResponseMock).toHaveBeenCalledWith({});
    });
});
