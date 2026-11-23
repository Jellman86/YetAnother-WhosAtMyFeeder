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

import { fetchAudioHiddenCount, fetchEventAudioContext, setAudioHidden, setAudioHiddenBulk } from './audio';

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

it('sends an explicit local visibility change as JSON and handles the response', async () => {
    const response = { ok: true };
    apiFetchMock.mockResolvedValue(response);
    handleResponseMock.mockResolvedValue({ id: 478, hidden: true });
    await expect(setAudioHidden(478, true)).resolves.toEqual({ id: 478, hidden: true });
    expect(apiFetchMock).toHaveBeenCalledWith('/api/audio/history/478', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: '{"hidden":true}'
    });
});

it('sends bulk local visibility changes as JSON and reads hidden counts', async () => {
    const response = { ok: true };
    apiFetchMock.mockResolvedValue(response);
    handleResponseMock.mockResolvedValueOnce({ updated_count: 2, ids: [10, 11], hidden: true });
    await expect(setAudioHiddenBulk([10, 11], true)).resolves.toEqual({ updated_count: 2, ids: [10, 11], hidden: true });
    expect(apiFetchMock).toHaveBeenCalledWith('/api/audio/history/visibility', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: '{"ids":[10,11],"hidden":true}'
    });

    handleResponseMock.mockResolvedValueOnce({ hidden_count: 4 });
    await expect(fetchAudioHiddenCount()).resolves.toEqual({ hidden_count: 4 });
    expect(apiFetchMock).toHaveBeenCalledWith('/api/audio/history/hidden-count', {
        signal: undefined,
        timeoutMs: 10_000
    });
});
