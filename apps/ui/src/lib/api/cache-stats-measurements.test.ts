import { afterEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock('./core', () => ({
    API_BASE: '/api', apiFetch: apiFetchMock,
    handleResponse: async (response: Response) => response.json()
}));
import { fetchCacheStats } from './maintenance';

function reply(status: string, id = 'measurement', size = 123): Response {
    return new Response(JSON.stringify({ id, status, stats: status === 'completed' ? { total_size_bytes: size } : null }));
}

afterEach(() => { vi.useRealTimers(); apiFetchMock.mockReset(); });

describe('storage measurements', () => {
    it('polls short requests using the same id until the completed result arrives', async () => {
        vi.useFakeTimers();
        apiFetchMock.mockResolvedValueOnce(reply('running')).mockResolvedValueOnce(reply('running')).mockResolvedValueOnce(reply('completed'));
        const result = fetchCacheStats();
        await vi.runAllTimersAsync();
        expect(await result).toEqual({ total_size_bytes: 123 });
        const urls = apiFetchMock.mock.calls.map(call => call[0]);
        expect(urls).toEqual(['/api/cache/measurement', '/api/cache/measurement?measurement_id=measurement', '/api/cache/measurement?measurement_id=measurement']);
        expect(apiFetchMock.mock.calls.every(call => call[1]?.timeoutMs <= 10_000)).toBe(true);
    });

    it('reports a failed measurement instead of returning an invented zero', async () => {
        apiFetchMock.mockResolvedValue(reply('failed'));
        await expect(fetchCacheStats()).rejects.toThrow('Storage measurement failed');
    });

    it('rejects an invalid response instead of polling forever', async () => {
        apiFetchMock.mockResolvedValue(new Response('{}'));
        await expect(fetchCacheStats()).rejects.toThrow('Invalid storage measurement response');
    });
});

it('coalesces callers in the same tab without duplicating poll requests', async () => {
    vi.useFakeTimers();
    apiFetchMock.mockResolvedValueOnce(reply('running')).mockResolvedValueOnce(reply('completed'));
    const first = fetchCacheStats();
    const second = fetchCacheStats();
    expect(first).toBe(second);
    await vi.runAllTimersAsync();
    expect(await first).toEqual(await second);
    expect(apiFetchMock).toHaveBeenCalledTimes(2);
});

it('starts once after an expired measurement id instead of looping on 404', async () => {
    vi.useFakeTimers();
    apiFetchMock.mockResolvedValueOnce(reply('running')).mockResolvedValueOnce(new Response('{}', { status: 404 })).mockResolvedValueOnce(reply('completed', 'new'));
    const result = fetchCacheStats();
    await vi.runAllTimersAsync();
    expect(await result).toEqual({ total_size_bytes: 123 });
    expect(apiFetchMock.mock.calls.map(call => call[0])).toEqual(['/api/cache/measurement', '/api/cache/measurement?measurement_id=measurement', '/api/cache/measurement']);
});

it('bounds how long a tab polls and preserves the id for an explicit retry', async () => {
    vi.useFakeTimers();
    apiFetchMock.mockImplementation(async () => reply('running', 'slow-measurement'));
    const result = fetchCacheStats();
    const rejected = expect(result).rejects.toThrow('still running');
    await vi.advanceTimersByTimeAsync(10 * 60_000);
    await rejected;
    apiFetchMock.mockImplementation(async () => reply('completed', 'slow-measurement'));
    await expect(fetchCacheStats()).resolves.toEqual({ total_size_bytes: 123 });
    expect(apiFetchMock.mock.calls.at(-1)?.[0]).toBe('/api/cache/measurement?measurement_id=slow-measurement');
});
