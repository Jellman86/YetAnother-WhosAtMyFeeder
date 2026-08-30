import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiRequestError, apiFetch, fetchWithAbort, handleResponse } from './core';

afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
});

describe('handleResponse', () => {
    it('formats JSON validation errors into readable messages', async () => {
        const response = new Response(
            JSON.stringify({
                detail: [
                    {
                        type: 'missing',
                        loc: ['body', 'frigate_url'],
                        msg: 'Field required',
                    },
                    {
                        type: 'value_error',
                        loc: ['body', 'auth_password'],
                        msg: 'Value error, Password must contain at least one letter and one number',
                    }
                ]
            }),
            {
                status: 422,
                headers: { 'Content-Type': 'application/json' }
            }
        );

        await expect(handleResponse(response)).rejects.toThrow(
            'frigate_url: Field required; auth_password: Password must contain at least one letter and one number'
        );
    });

    it('aborts a background request after its explicit timeout', async () => {
        vi.useFakeTimers();
        vi.stubGlobal('fetch', vi.fn((_url: string, options?: RequestInit) => new Promise<Response>((_resolve, reject) => {
            options?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
        })));

        const request = apiFetch('/api/background-status', { timeoutMs: 5000 });
        const rejection = expect(request).rejects.toMatchObject({ name: 'AbortError' });
        await vi.advanceTimersByTimeAsync(5000);

        await rejection;
    });

    it('keeps the newest keyed request cancellable after an older request settles', async () => {
        type PendingFetch = {
            resolve: (response: Response) => void;
            signal: AbortSignal | null | undefined;
        };
        const pending: PendingFetch[] = [];
        vi.stubGlobal('fetch', vi.fn((_url: string, options?: RequestInit) => new Promise<Response>((resolve, reject) => {
            const signal = options?.signal;
            signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
            pending.push({ resolve, signal });
        })));

        const firstResult = fetchWithAbort('events-page', '/api/events?offset=0').catch((error) => error);
        const secondResult = fetchWithAbort('events-page', '/api/events?offset=25').catch((error) => error);
        await firstResult;

        const thirdRequest = fetchWithAbort<{ ok: boolean }>('events-page', '/api/events?offset=50');

        expect(pending[1].signal?.aborted).toBe(true);
        pending[2].resolve(new Response(JSON.stringify({ ok: true }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
        }));

        await secondResult;
        await expect(thirdRequest).resolves.toEqual({ ok: true });
    });
});

describe('ApiRequestError', () => {
    it('keeps the HTTP status so callers can tell absence from failure', async () => {
        const response = new Response(JSON.stringify({ detail: 'Detection not found' }), {
            status: 404,
            headers: { 'Content-Type': 'application/json' }
        });

        const outcome = await handleResponse(response).then(
            () => null,
            (e: unknown) => e
        );
        expect(outcome).toBeInstanceOf(ApiRequestError);
        expect((outcome as ApiRequestError).status).toBe(404);
        expect((outcome as ApiRequestError).message).toBe('Detection not found');
    });
});
