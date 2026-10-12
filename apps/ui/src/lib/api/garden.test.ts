import { afterEach, describe, expect, it, vi } from 'vitest';
import { setApiKey, setAuthToken } from './core';
import { identifyGarden } from './garden';

afterEach(() => {
    setAuthToken(null);
    setApiKey(null);
    vi.unstubAllGlobals();
});

describe('garden species suggestion requests', () => {
    it('delivers a JSON request to the owner-only endpoint', async () => {
        setAuthToken('owner-session');
        let received: Request | undefined;
        vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
            received = new Request(`http://localhost${url}`, options);
            return new Response('{}', { headers: { 'Content-Type': 'application/json' } });
        }));

        await identifyGarden('capture 1', { variant: '4.0.3b', provider: 'intel_npu' });

        expect(received?.url).toBe('http://localhost/api/garden/capture%201/identify');
        expect(received?.method).toBe('POST');
        expect(received?.headers.get('Authorization')).toBe('Bearer owner-session');
        expect(received?.headers.get('Content-Type')).toBe('application/json');
        expect(await received?.json()).toEqual({ variant: '4.0.3b', provider: 'intel_npu' });
    });
});
