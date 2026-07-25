import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock, handleResponseMock } = vi.hoisted(() => ({
    apiFetchMock: vi.fn(),
    handleResponseMock: vi.fn()
}));

vi.mock('./core', () => ({
    API_BASE: '/api',
    apiFetch: apiFetchMock,
    handleResponse: handleResponseMock
}));

import { fetchSystemTelemetry } from './system';

describe('system telemetry', () => {
    beforeEach(() => {
        apiFetchMock.mockReset();
        handleResponseMock.mockReset();
    });

    it('fetches one uncached bounded telemetry sample', async () => {
        const response = new Response('{}');
        const sample = {
            sampled_at: '2026-07-25T12:00:00Z',
            cpu_percent: 37.5,
            accelerator: { kind: 'npu', label: 'NPU', utilization_percent: 18.2 }
        };
        apiFetchMock.mockResolvedValue(response);
        handleResponseMock.mockResolvedValue(sample);

        await expect(fetchSystemTelemetry()).resolves.toEqual(sample);
        expect(apiFetchMock).toHaveBeenCalledWith('/api/system-telemetry', {
            cache: 'no-store',
            timeoutMs: 2_500
        });
        expect(handleResponseMock).toHaveBeenCalledWith(response);
    });
});
